<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Company;
use App\Models\ItTask;
use App\Models\Resume;
use App\Support\ResumeOptions;
use App\Support\Seo;
use Illuminate\Database\Eloquent\Builder;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Страница направления «Доп. услуг»: IT-услуги, HR-услуги, подбор
 * персонала, логистика, декларирование, бухгалтерия.
 *
 * Лента /it-services показывает задачи всех направлений с фильтром;
 * здесь — всё про одно направление на одной странице: что это,
 * сколько задач и исполнителей, открытые и выполненные задачи,
 * исполнители, у HR — ещё и резюме. Сюда ведёт подменю «Доп. услуги»
 * в шапке.
 */
class ServiceSectionController extends Controller
{
    /** Открытых задач на странице; остальные — в ленте с фильтром. */
    private const TASKS = 6;

    private const COMPLETED = 3;

    private const PROVIDERS = 8;

    private const RESUMES = 6;

    /** Направления, у которых на странице есть резюме. */
    private const WITH_RESUMES = ['hr_services', 'hr'];

    public function show(string $slug): Response
    {
        $code = ItTask::SERVICE_PAGES[$slug] ?? abort(404);
        $types = ItTask::typesUnder($code);

        $tasks = fn (): Builder => ItTask::query()
            ->with(['company.city.translations', 'contractor'])
            ->whereIn('service_type', $types)
            ->whereHas('company', fn (Builder $q) => $q->where('status', Company::STATUS_ACTIVE));

        $providers = $this->providers($types);
        $withResumes = in_array($code, self::WITH_RESUMES, true);

        app(Seo::class)
            ->title(__("ui.service_pages.{$slug}.title"))
            ->description(__("ui.service_pages.{$slug}.lead"))
            ->canonical(url('/services/'.$slug));

        return Inertia::render('it-tasks/Section', [
            'section' => [
                'slug' => $slug,
                'code' => $code,
                'title' => __("ui.service_pages.{$slug}.title"),
                'lead' => __("ui.service_pages.{$slug}.lead"),
                'offers' => __("ui.service_pages.{$slug}.offers"),
            ],
            'stats' => [
                'active' => $tasks()->active()->count(),
                'completed' => $tasks()->completed()->count(),
                'providers' => $providers->count(),
                'resumes' => $withResumes ? Resume::query()->published()->count() : null,
            ],
            'kinds' => $this->kinds($code),
            'tasks' => $tasks()->active()
                ->orderByDesc('published_at')
                ->orderByDesc('id')
                ->limit(self::TASKS)
                ->get()
                ->map(fn (ItTask $t): array => ItTaskController::card($t))
                ->values(),
            'completed' => $tasks()->completed()
                ->orderByDesc('completed_at')
                ->orderByDesc('id')
                ->limit(self::COMPLETED)
                ->get()
                ->map(fn (ItTask $t): array => ItTaskController::card($t))
                ->values(),
            'providers' => (clone $providers)
                ->with('city.translations')
                ->orderByDesc('verification_level')
                ->orderByDesc('rating')
                ->orderBy('id')
                ->limit(self::PROVIDERS)
                ->get()
                ->map(fn (Company $c): array => [
                    'slug' => $c->slug,
                    'name' => $c->name,
                    'city' => $c->city?->name(),
                    'verification_level' => $c->verification_level,
                    'rating' => (float) $c->rating,
                    'initials' => $c->initials(),
                    'logo' => $c->logoUrl(),
                    'specializations' => array_values(array_map(
                        fn (string $type): string => __('ui.it_tasks.types.'.$type),
                        array_intersect($c->it_specializations ?? [], $types),
                    )),
                ])
                ->values(),
            'resumes' => $withResumes
                ? Resume::query()
                    ->with(['city.translations', 'country.translations', 'user'])
                    ->published()
                    ->latest('published_at')
                    ->latest('id')
                    ->limit(self::RESUMES)
                    ->get()
                    ->map(fn (Resume $r): array => ResumeController::card($r))
                    ->values()
                : [],
            'resumeFields' => $withResumes ? ResumeOptions::fields() : (object) [],
            'pages' => array_map(fn (string $page): array => [
                'slug' => $page,
                'title' => __("ui.service_pages.{$page}.title"),
            ], ItTask::serviceMenu()),
        ]);
    }

    /**
     * Исполнители направления: компании-исполнители, у которых в
     * специализациях есть хоть один вид этого направления.
     *
     * @param  list<string>  $types
     * @return Builder<Company>
     */
    private function providers(array $types): Builder
    {
        return Company::query()
            ->where('status', Company::STATUS_ACTIVE)
            ->where('is_it_provider', true)
            ->where(function (Builder $q) use ($types): void {
                foreach ($types as $type) {
                    $q->orWhereJsonContains('it_specializations', $type);
                }
            });
    }

    /**
     * Что входит в направление — плитки со ссылками и счётчиками.
     *
     * У IT это семь видов (ведут в ленту с фильтром), у HR — подбор
     * персонала (своя страница) и резюме. У остальных направлений
     * видов нет — плиток тоже.
     *
     * @return list<array{label: string, href: string, count: int, kind: string}>
     */
    private function kinds(string $code): array
    {
        $counts = ItTask::query()
            ->active()
            ->whereHas('company', fn (Builder $q) => $q->where('status', Company::STATUS_ACTIVE))
            ->selectRaw('service_type, count(*) as total')
            ->groupBy('service_type')
            ->pluck('total', 'service_type');

        if ($code === 'hr_services') {
            return [
                [
                    'label' => __('ui.it_tasks.types.hr'),
                    'href' => '/services/recruitment',
                    'count' => (int) ($counts['hr'] ?? 0),
                    'kind' => 'tasks',
                ],
                [
                    'label' => __('ui.nav.resumes'),
                    'href' => '/resumes',
                    'count' => Resume::query()->published()->count(),
                    'kind' => 'resumes',
                ],
            ];
        }

        return array_map(fn (string $type): array => [
            'label' => __('ui.it_tasks.types.'.$type),
            'href' => '/it-services?type='.$type,
            'count' => (int) ($counts[$type] ?? 0),
            'kind' => 'tasks',
        ], ItTask::SERVICE_SECTIONS[$code] ?? []);
    }
}
