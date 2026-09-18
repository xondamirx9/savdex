<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\City;
use App\Models\Resume;
use App\Support\ResumeOptions;
use App\Support\Seo;
use Illuminate\Contracts\Database\Eloquent\Builder;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Раздел «Резюме»: кого можно нанять.
 *
 * Бесплатный с обеих сторон: соискатель публикует без оплаты,
 * компания смотрит без списания кредитов. Контакты открыты, но
 * только вошедшим — резюме не должно утекать поисковым роботам
 * и сборщикам баз вместе с телефоном живого человека.
 */
class ResumeController extends Controller
{
    private const PER_PAGE = 20;

    public function index(Request $request): Response
    {
        $query = trim($request->string('q')->toString());
        $field = $request->string('field')->toString();
        $experience = $request->string('experience')->toString();

        $resumes = Resume::query()
            ->with(['city.translations', 'country.translations'])
            ->published()
            ->when($query !== '', fn (Builder $q) => $q->search($query))
            ->when(in_array($field, ResumeOptions::FIELDS, true), fn (Builder $q) => $q->where('field', $field))
            ->when($request->integer('city'), fn (Builder $q, int $id) => $q->where('city_id', $id))
            ->when(
                array_key_exists($experience, ResumeOptions::EXPERIENCE_STEPS),
                fn (Builder $q) => $q->where('experience_months', '>=', Resume::experienceAtLeast($experience)),
            )
            ->when($request->string('employment')->toString(), fn (Builder $q, string $value) => $q
                ->whereJsonContains('employment', $value))
            ->latest('published_at')
            ->latest('id')
            ->paginate(self::PER_PAGE)
            ->withQueryString();

        app(Seo::class)
            ->title(__('ui.resume.meta_title'))
            ->description(__('ui.resume.meta_description'))
            ->canonical(url('/resumes'))
            ->noindex($request->hasAny(['q', 'field', 'city', 'experience', 'employment']) || $resumes->currentPage() > 1);

        return Inertia::render('resumes/Index', [
            'resumes' => $resumes->through(fn (Resume $r): array => $this->card($r)),
            'filters' => [
                'q' => $query,
                'field' => $field !== '' ? $field : null,
                'city' => $request->integer('city') ?: null,
                'experience' => $experience !== '' ? $experience : null,
                'employment' => $request->string('employment')->toString() ?: null,
            ],
            'options' => [
                'fields' => ResumeOptions::fields(),
                'experience' => ResumeOptions::experienceSteps(),
                'employment' => ResumeOptions::employment(),
            ],
            'cities' => $this->cities(),
            'total' => $resumes->total(),
        ]);
    }

    public function show(Request $request, string $slug): Response
    {
        $resume = Resume::query()
            ->with(['city.translations', 'country.translations', 'user'])
            ->published()
            ->where('slug', $slug)
            ->firstOrFail();

        // Свой просмотр не считаем: иначе счётчик показывает, сколько
        // раз человек сам открыл собственное резюме
        if ($request->user()?->id !== $resume->user_id) {
            $resume->increment('views_count');
        }

        $description = Str::limit(trim((string) $resume->localizedAbout()), 160);

        app(Seo::class)
            ->title($resume->localizedTitle())
            ->description($description !== '' ? $description : __('ui.resume.meta_description'))
            ->canonical(url('/resume/'.$resume->slug));

        return Inertia::render('resumes/Show', [
            'resume' => [
                ...$this->card($resume),
                'about' => $resume->localizedAbout(),
                'jobs' => $resume->localizedJobs(),
                'education' => $resume->education ?? [],
                'languages' => $resume->languages ?? [],
                'schedule' => $resume->schedule ?? [],
                'views' => $resume->views_count,

                /*
                 * Контакты — только вошедшим. Раздел бесплатный, кредиты
                 * за раскрытие не списываются, но отдавать телефон
                 * человека анониму и поисковому роботу площадка не будет.
                 */
                'contacts' => $request->user() === null ? null : array_filter([
                    'name' => $resume->contact_name ?: $resume->user?->name,
                    'phone' => $resume->show_phone ? $resume->contact_phone : null,
                    'email' => $resume->show_email ? $resume->contact_email : null,
                ]),
            ],
            'options' => [
                'fields' => ResumeOptions::fields(),
                'employment' => ResumeOptions::employment(),
                'schedule' => ResumeOptions::schedule(),
                'language_levels' => ResumeOptions::languageLevels(),
                'education_levels' => ResumeOptions::educationLevels(),
            ],
            'similar' => Resume::query()
                ->with(['city.translations', 'country.translations'])
                ->published()
                ->where('id', '!=', $resume->id)
                ->when($resume->field, fn (Builder $q, string $field) => $q->where('field', $field))
                ->latest('published_at')
                ->limit(4)
                ->get()
                ->map(fn (Resume $r): array => $this->card($r))
                ->values(),
        ]);
    }

    /** @return array<string, mixed> */
    private function card(Resume $resume): array
    {
        return [
            'id' => $resume->id,
            'slug' => $resume->slug,
            'title' => $resume->localizedTitle(),
            'field' => $resume->field,
            'name' => $resume->contact_name ?: $resume->user?->name,
            'initials' => $resume->initials(),
            'photo' => $resume->photoUrl(),
            'city' => $resume->city?->name(),
            'country' => $resume->country?->name(),
            'salary' => $resume->salary !== null ? (int) $resume->salary : null,
            'currency' => $resume->currency,
            'employment' => $resume->employment ?? [],
            'experience' => $resume->experience(),
            'skills' => array_slice($resume->skills ?? [], 0, 8),
            'published' => $resume->published_at?->translatedFormat('d.m.Y'),
        ];
    }

    /**
     * Города, в которых есть хотя бы одно опубликованное резюме:
     * список из трёхсот городов в фильтре, где занято четыре,
     * искать в нём мешает.
     *
     * @return list<array{id: int, name: string}>
     */
    private function cities(): array
    {
        return City::query()
            ->where('is_active', true)
            ->with('translations')
            ->whereHas('resumes', fn (Builder $q) => $q->where('status', Resume::STATUS_PUBLISHED))
            ->get()
            ->map(fn (City $c): array => ['id' => $c->id, 'name' => $c->name()])
            ->sortBy('name')
            ->values()
            ->all();
    }
}
