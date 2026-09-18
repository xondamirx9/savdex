<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\City;
use App\Models\Company;
use App\Models\ItTask;
use App\Models\ItTaskFile;
use App\Support\DateHelper;
use App\Support\Seo;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use Inertia\Inertia;
use Inertia\Response;
use Symfony\Component\HttpFoundation\StreamedResponse;

/**
 * Витрина IT-услуг: открытые IT-задачи компаний и карточка задачи.
 *
 * Откликаются только компании с ролью IT-исполнителя; кнопка ведёт
 * в тот же чат, что и отклик на объявление. Файлы ТЗ — только
 * вошедшим: техзадание не должно индексироваться и уходить по
 * прямой ссылке.
 */
class ItTaskController extends Controller
{
    private const PER_PAGE = 20;

    public function index(Request $request): Response
    {
        $query = trim($request->string('q')->toString());
        $type = $request->string('type')->toString();
        // Фильтровать можно и по направлению («IT-услуги»), и по виду
        // внутри него — в адресе они выглядят одинаково
        $type = in_array($type, ItTask::filterableTypes(), true) ? $type : '';
        $done = $request->boolean('done');
        $city = $request->integer('city');
        $verified = $request->boolean('verified');
        $withBudget = $request->boolean('with_budget');

        $tasks = ItTask::query()
            ->with(['company.city.translations', 'contractor'])
            ->when($done, fn (Builder $q) => $q->completed(), fn (Builder $q) => $q->active())
            ->whereHas('company', fn (Builder $q) => $q->where('status', 'active'))
            ->when($query !== '', fn (Builder $q) => $q->search($query))
            ->when($type !== '', fn (Builder $q) => $q->whereIn('service_type', ItTask::typesUnder($type)))
            ->when($city !== 0, fn (Builder $q) => $q->whereHas(
                'company',
                fn (Builder $c) => $c->where('city_id', $city),
            ))
            // Уровень 2 — тот же порог, что у бейджа «Проверена»
            // в каталоге: иначе одна и та же галочка означала бы
            // на двух страницах разное
            ->when($verified, fn (Builder $q) => $q->whereHas(
                'company',
                fn (Builder $c) => $c->where('verification_level', '>=', 2),
            ))
            // «Договорной» — это отсутствие суммы, а не сумма ноль
            ->when($withBudget, fn (Builder $q) => $q->where('budget_type', '!=', 'negotiable'))
            ->tap(fn (Builder $q) => $done ? $q->orderByDesc('completed_at') : $q->orderByDesc('published_at'))
            ->orderByDesc('id')
            ->paginate(self::PER_PAGE)
            ->withQueryString();

        app(Seo::class)
            ->title(__('ui.it_tasks.meta_title'))
            ->description(__('ui.it_tasks.meta_description'))
            ->canonical(url('/it-services'))
            // Отфильтрованная выборка — не самостоятельная страница:
            // десятки сочетаний фильтров в индексе выглядят как дубли
            ->noindex($query !== '' || $type !== '' || $city !== 0 || $verified || $withBudget
                || $tasks->currentPage() > 1);

        return Inertia::render('it-tasks/Index', [
            'tasks' => $tasks->through(fn (ItTask $t): array => $this->card($t)),
            'filters' => [
                'q' => $query,
                'type' => $type,
                'done' => $done,
                'city' => $city ?: null,
                'verified' => $verified,
                'with_budget' => $withBudget,
            ],
            'types' => $this->types(),
            'cities' => $this->cities(),
            'total' => $tasks->total(),
            'viewer' => $this->viewer($request),
        ]);
    }

    public function show(Request $request, string $slug): Response
    {
        $task = ItTask::query()
            ->with(['company.city.translations', 'contractor', 'files'])
            ->where('slug', $slug)
            ->firstOrFail();

        $viewerCompanyId = $request->user()?->company_id;
        $isOwner = $viewerCompanyId !== null && $viewerCompanyId === $task->company_id;

        // Открытые и выполненные — публичны; закрытую без результата
        // видит только заказчик, чтобы исполнители не откликались в пустоту
        abort_if(! $task->isActive() && ! $task->isCompleted() && ! $isOwner, 404);

        if (! $isOwner) {
            $task->increment('views_count');
        }

        app(Seo::class)
            ->title($task->title)
            ->description(Str::limit($task->description, 160))
            ->canonical(url('/it-services/'.$task->slug))
            ->noindex(! $task->isActive());

        $similar = ItTask::query()
            ->with('company.city.translations')
            ->active()
            ->where('id', '!=', $task->id)
            ->where('service_type', $task->service_type)
            ->orderByDesc('published_at')
            ->limit(3)
            ->get();

        $company = $request->user()?->company;

        return Inertia::render('it-tasks/Show', [
            'task' => [
                ...$this->card($task),
                'description' => preg_split('/\R{2,}/u', trim($task->description)) ?: [],
                'files' => $task->files->map(fn (ItTaskFile $f): array => [
                    'id' => $f->id,
                    'title' => $f->title,
                    'size' => $f->sizeLabel(),
                    'ext' => $f->extension(),
                ])->values(),
                'views' => $task->views_count,
            ],
            'respond' => [
                'guest' => $request->user() === null,
                'owner' => $isOwner,
                'no_company' => $request->user() !== null && $company === null,
                'provider' => (bool) $company?->is_it_provider,
            ],
            'similar' => $similar->map(fn (ItTask $t): array => $this->card($t))->values(),
        ]);
    }

    /** Файл ТЗ — только вошедшим и только к открытой задаче (или своей). */
    public function file(Request $request, int $id): StreamedResponse
    {
        $file = ItTaskFile::query()->with('task')->find($id);
        abort_if($file === null || $file->task === null, 404);

        $task = $file->task;
        $isOwner = $request->user()?->company_id === $task->company_id;

        abort_unless($task->isActive() || $isOwner, 404);
        abort_unless(Storage::disk('local')->exists($file->file_path), 404);

        $name = trim(preg_replace('#[/\\\\]+#', '-', $file->title) ?? '', ' .-');

        return Storage::disk('local')->download($file->file_path, $name !== '' ? $name : 'file');
    }

    // ── Представление ────────────────────────────────────────

    /** @return array<string, mixed> */
    private function card(ItTask $task): array
    {
        return [
            'id' => $task->id,
            'slug' => $task->slug,
            'title' => $task->title,
            'excerpt' => Str::limit(trim($task->description), 180),
            'service_type' => $task->service_type,
            'service_label' => __('ui.it_tasks.types.'.$task->service_type),
            'stack' => $task->stack ?? [],
            'budget_type' => $task->budget_type,
            'budget_from' => $task->budget_from !== null ? (float) $task->budget_from : null,
            'budget_to' => $task->budget_to !== null ? (float) $task->budget_to : null,
            'currency' => $task->currency,
            'deadline' => DateHelper::dayMonthYear($task->deadline_at),
            'published' => DateHelper::dayMonthYear($task->published_at),
            'responses' => $task->responses_count,
            'active' => $task->isActive(),
            'completed' => $task->isCompleted(),
            'completed_on' => DateHelper::dayMonthYear($task->completed_at),
            'result_url' => $task->isCompleted() ? $task->result_url : null,
            'result_host' => $task->isCompleted() && $task->result_url !== null
                ? (string) preg_replace('#^www\.#', '', (string) parse_url($task->result_url, PHP_URL_HOST))
                : null,
            'result_summary' => $task->isCompleted() ? $task->result_summary : null,
            'contractor' => $task->isCompleted() && $task->contractor !== null ? [
                'name' => $task->contractor->name,
                'slug' => $task->contractor->slug,
                'initials' => $task->contractor->initials(),
                'logo' => $task->contractor->logoUrl(),
            ] : null,
            'company' => $task->company === null ? null : [
                'name' => $task->company->name,
                'slug' => $task->company->slug,
                'initials' => $task->company->initials(),
                'logo' => $task->company->logoUrl(),
                'verified' => $task->company->verification_level >= 2,
                'city' => $task->company->city?->name(),
            ],
        ];
    }

    /** @return list<array{code: string, label: string}> */
    /**
     * Дерево направлений для панели фильтра.
     *
     * @return list<array{code: string, label: string, children: list<array{code: string, label: string}>}>
     */
    private function types(): array
    {
        return array_map(fn (string $code): array => [
            'code' => $code,
            'label' => __('ui.it_tasks.types.'.$code),
            'children' => array_map(fn (string $child): array => [
                'code' => $child,
                'label' => __('ui.it_tasks.types.'.$child),
            ], ItTask::SERVICE_SECTIONS[$code]),
        ], array_keys(ItTask::SERVICE_SECTIONS));
    }

    /**
     * Города для фильтра.
     *
     * Обычно — только те, где задачи действительно есть: полный
     * справочник заставляет выбирать Нукус и получать пустую ленту,
     * не понимая, дело в фильтре или задач нет вовсе.
     *
     * Но если город не указан ни у одной компании с задачами, список
     * оказывается пустым, и фильтр пропадает с панели целиком — рядом
     * с каталогом, где город есть всегда, это выглядит недоделкой.
     * В этом случае показываем все города: выбор хотя бы работает,
     * а как только компании заполнят профиль, список сам сузится.
     *
     * @return list<array{id: int, name: string}>
     */
    private function cities(): array
    {
        $ids = Company::query()
            ->where('status', 'active')
            ->whereNotNull('city_id')
            ->whereIn('id', ItTask::query()->active()->select('company_id'))
            ->distinct()
            ->pluck('city_id');

        return City::query()
            ->where('is_active', true)
            ->when($ids->isNotEmpty(), fn (Builder $q) => $q->whereIn('id', $ids))
            ->with('translations')
            ->get()
            ->map(fn (City $c): array => ['id' => $c->id, 'name' => $c->name()])
            ->sortBy('name')
            ->values()
            ->all();
    }

    /** @return array{guest: bool, provider: bool} */
    private function viewer(Request $request): array
    {
        return [
            'guest' => $request->user() === null,
            'provider' => (bool) $request->user()?->company?->is_it_provider,
        ];
    }
}
