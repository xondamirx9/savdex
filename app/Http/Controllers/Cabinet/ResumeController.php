<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\City;
use App\Models\Country;
use App\Models\Resume;
use App\Support\Currencies;
use App\Support\ImageStore;
use App\Support\ResumeOptions;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;
use Inertia\Inertia;
use Inertia\Response;

/**
 * «Моё резюме» — кабинет соискателя.
 *
 * Резюме одно на человека и бесплатное: раздел нужен не для продажи
 * доступа, а чтобы привести на площадку людей, которых ищут её же
 * компании. Поэтому ни тарифа, ни лимитов здесь нет.
 *
 * Черновик виден только владельцу. Публикация мгновенная, без
 * ожидания модерации: человек, который ищет работу, не должен ждать
 * сутки — а снять неподходящее резюме модератор может и потом.
 */
class ResumeController extends Controller
{
    public function edit(Request $request): Response
    {
        $user = $request->user();
        $resume = Resume::query()->where('user_id', $user->id)->first();

        return Inertia::render('cabinet/Resume', [
            'resume' => $resume === null ? null : $this->present($resume),

            // Заготовка для первого захода: имя и контакты берём
            // из профиля, чтобы человек не переписывал их руками
            'defaults' => [
                'contact_name' => $user->name,
                'contact_email' => $user->email,
                'contact_phone' => $user->phone,
            ],

            'options' => [
                'fields' => ResumeOptions::fields(),
                'employment' => ResumeOptions::employment(),
                'schedule' => ResumeOptions::schedule(),
                'language_levels' => ResumeOptions::languageLevels(),
                'education_levels' => ResumeOptions::educationLevels(),
                'currencies' => Currencies::labels(),
            ],

            'countries' => Country::listed()
                ->map(fn (Country $c): array => ['id' => $c->id, 'name' => $c->name()]),

            'cities' => City::query()->where('is_active', true)->with('translations')->orderBy('sort')->get()
                ->map(fn (City $c): array => ['id' => $c->id, 'name' => $c->name(), 'country_id' => $c->country_id]),
        ]);
    }

    public function update(Request $request): RedirectResponse
    {
        $data = $this->validated($request);

        // Не firstOrNew по user_id: он не в списке заполняемых полей,
        // и владельца резюме не должен назначать присланный запрос
        $resume = Resume::query()->where('user_id', $request->user()->id)->first() ?? new Resume;

        $resume->fill($data);
        $resume->user_id = $request->user()->id;

        // Опыт считаем здесь: по нему работает фильтр «от трёх лет»,
        // а складывать периоды в запросе нельзя — они лежат в json
        $resume->experience_months = Resume::experienceMonths($resume->jobs);

        $resume->save();

        if (blank($resume->slug)) {
            $resume->slug = Resume::makeSlug($resume->title, $resume->id);
            $resume->saveQuietly();
        }

        return back()->with('status', __('ui.messages.resume.saved'));
    }

    /** Публикация и снятие — одной кнопкой, без ожидания проверки. */
    public function publish(Request $request): RedirectResponse
    {
        $resume = $this->own($request);

        if ($resume->status === Resume::STATUS_BLOCKED) {
            return back()->withErrors(['status' => __('ui.messages.resume.blocked')]);
        }

        $resume->forceFill([
            'status' => Resume::STATUS_PUBLISHED,
            'published_at' => $resume->published_at ?? now(),
        ])->save();

        return back()->with('status', __('ui.messages.resume.published'));
    }

    public function hide(Request $request): RedirectResponse
    {
        $resume = $this->own($request);

        if ($resume->status === Resume::STATUS_PUBLISHED) {
            $resume->forceFill(['status' => Resume::STATUS_HIDDEN])->save();
        }

        return back()->with('status', __('ui.messages.resume.hidden'));
    }

    public function photo(Request $request, ImageStore $images): RedirectResponse
    {
        $request->validate(['photo' => ['required', 'image', 'max:5120']]);

        $resume = $this->own($request);
        $previous = $resume->photo_path;

        $resume->forceFill([
            'photo_path' => $images->store($request->file('photo'), 'resumes', [400, 400]),
        ])->save();

        $images->delete($previous);

        return back()->with('status', __('ui.messages.resume.photo_saved'));
    }

    public function destroy(Request $request, ImageStore $images): RedirectResponse
    {
        $resume = $this->own($request);

        $images->delete($resume->photo_path);
        $resume->delete();

        return back()->with('status', __('ui.messages.resume.deleted'));
    }

    // ── Внутреннее ───────────────────────────────────────────

    private function own(Request $request): Resume
    {
        return Resume::query()->where('user_id', $request->user()->id)->firstOrFail();
    }

    /** @return array<string, mixed> */
    private function validated(Request $request): array
    {
        $data = $request->validate([
            'title' => ['required', 'string', 'min:3', 'max:120'],
            'field' => ['nullable', Rule::in(ResumeOptions::FIELDS)],
            'country_id' => ['nullable', 'integer', 'exists:countries,id'],
            'city_id' => ['nullable', 'integer', 'exists:cities,id'],
            'salary' => ['nullable', 'integer', 'min:0', 'max:1000000000'],
            'currency' => ['nullable', Rule::in(Currencies::codes())],

            'employment' => ['nullable', 'array'],
            'employment.*' => [Rule::in(ResumeOptions::EMPLOYMENT)],
            'schedule' => ['nullable', 'array'],
            'schedule.*' => [Rule::in(ResumeOptions::SCHEDULE)],

            'about' => ['nullable', 'string', 'max:5000'],

            'skills' => ['nullable', 'array', 'max:30'],
            // nullable обязателен: пустая строка из формы приходит
            // сюда уже как null (ConvertEmptyStringsToNull), и без
            // него лишняя пустая строка навыков роняла всю форму
            'skills.*' => ['nullable', 'string', 'max:40'],

            'jobs' => ['nullable', 'array', 'max:20'],
            'jobs.*.company' => ['nullable', 'string', 'max:190'],
            'jobs.*.position' => ['required_with:jobs.*.company', 'nullable', 'string', 'max:190'],
            'jobs.*.start' => ['nullable', 'string', 'max:7'],
            'jobs.*.end' => ['nullable', 'string', 'max:7'],
            'jobs.*.duties' => ['nullable', 'string', 'max:2000'],

            'education' => ['nullable', 'array', 'max:10'],
            'education.*.institution' => ['nullable', 'string', 'max:190'],
            'education.*.faculty' => ['nullable', 'string', 'max:190'],
            'education.*.level' => ['nullable', Rule::in(ResumeOptions::EDUCATION_LEVELS)],
            'education.*.year' => ['nullable', 'integer', 'between:1950,'.(date('Y') + 10)],

            'languages' => ['nullable', 'array', 'max:10'],
            'languages.*.name' => ['nullable', 'string', 'max:40'],
            'languages.*.level' => ['nullable', Rule::in(ResumeOptions::LANGUAGE_LEVELS)],

            'contact_name' => ['nullable', 'string', 'max:190'],
            'contact_phone' => ['nullable', 'string', 'max:32'],
            'contact_email' => ['nullable', 'email', 'max:190'],
            'show_phone' => ['boolean'],
            'show_email' => ['boolean'],
        ]);

        // Пустые строки репитеров выкидываем: строка без должности
        // и без места работы — это забытая пустая карточка, а не опыт
        $data['jobs'] = $this->clean($data['jobs'] ?? [], ['company', 'position']);
        $data['education'] = $this->clean($data['education'] ?? [], ['institution']);
        $data['languages'] = $this->clean($data['languages'] ?? [], ['name']);
        $data['skills'] = array_values(array_filter(
            array_map(fn (mixed $skill): string => trim((string) $skill), $data['skills'] ?? []),
            fn (string $skill): bool => $skill !== '',
        ));

        return $data;
    }

    /**
     * @param  list<array<string, mixed>>  $rows
     * @param  list<string>  $required  хотя бы одно из этих полей заполнено
     * @return list<array<string, mixed>>
     */
    private function clean(array $rows, array $required): array
    {
        return array_values(array_filter($rows, function (array $row) use ($required): bool {
            foreach ($required as $key) {
                if (trim((string) ($row[$key] ?? '')) !== '') {
                    return true;
                }
            }

            return false;
        }));
    }

    /** @return array<string, mixed> */
    private function present(Resume $resume): array
    {
        return [
            'id' => $resume->id,
            'slug' => $resume->slug,
            'title' => $resume->title,
            'field' => $resume->field,
            'country_id' => $resume->country_id,
            'city_id' => $resume->city_id,
            'salary' => $resume->salary,
            'currency' => $resume->currency,
            'employment' => $resume->employment ?? [],
            'schedule' => $resume->schedule ?? [],
            'about' => $resume->about,
            'skills' => $resume->skills ?? [],
            'jobs' => $resume->jobs ?? [],
            'education' => $resume->education ?? [],
            'languages' => $resume->languages ?? [],
            'contact_name' => $resume->contact_name,
            'contact_phone' => $resume->contact_phone,
            'contact_email' => $resume->contact_email,
            'show_phone' => $resume->show_phone,
            'show_email' => $resume->show_email,
            'photo' => $resume->photoUrl(),
            'status' => $resume->status,
            'moderation_note' => $resume->moderation_note,
            'views' => $resume->views_count,
            'experience' => $resume->experience(),
        ];
    }
}
