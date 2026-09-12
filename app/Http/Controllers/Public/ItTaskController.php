<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
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
        $type = array_key_exists($type, ItTask::SERVICE_TYPES) ? $type : '';

        $tasks = ItTask::query()
            ->with('company')
            ->active()
            ->whereHas('company', fn (Builder $q) => $q->where('status', 'active'))
            ->when($query !== '', fn (Builder $q) => $q->search($query))
            ->when($type !== '', fn (Builder $q) => $q->where('service_type', $type))
            ->orderByDesc('published_at')
            ->orderByDesc('id')
            ->paginate(self::PER_PAGE)
            ->withQueryString();

        app(Seo::class)
            ->title(__('ui.it_tasks.meta_title'))
            ->description(__('ui.it_tasks.meta_description'))
            ->canonical(url('/it-services'))
            ->noindex($query !== '' || $type !== '' || $tasks->currentPage() > 1);

        return Inertia::render('it-tasks/Index', [
            'tasks' => $tasks->through(fn (ItTask $t): array => $this->card($t)),
            'filters' => ['q' => $query, 'type' => $type],
            'types' => $this->types(),
            'total' => $tasks->total(),
            'viewer' => $this->viewer($request),
        ]);
    }

    public function show(Request $request, string $slug): Response
    {
        $task = ItTask::query()
            ->with(['company', 'files'])
            ->where('slug', $slug)
            ->firstOrFail();

        $viewerCompanyId = $request->user()?->company_id;
        $isOwner = $viewerCompanyId !== null && $viewerCompanyId === $task->company_id;

        // Закрытую задачу видит только её заказчик — остальным 404,
        // чтобы исполнители не откликались в пустоту
        abort_if(! $task->isActive() && ! $isOwner, 404);

        if (! $isOwner) {
            $task->increment('views_count');
        }

        app(Seo::class)
            ->title($task->title)
            ->description(Str::limit($task->description, 160))
            ->canonical(url('/it-services/'.$task->slug))
            ->noindex(! $task->isActive());

        $similar = ItTask::query()
            ->with('company')
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
    private function types(): array
    {
        return array_map(
            fn (string $code): array => ['code' => $code, 'label' => __('ui.it_tasks.types.'.$code)],
            array_keys(ItTask::SERVICE_TYPES),
        );
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
