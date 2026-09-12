<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\ItTask;
use App\Models\ItTaskFile;
use App\Support\DateHelper;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
use Illuminate\Validation\Rule;
use Inertia\Inertia;
use Inertia\Response;

/**
 * IT-задачи компании: публикация, правка, закрытие.
 *
 * Одна форма вместо мастера: у задачи меньше полей, чем у объявления,
 * и разбивать её на шаги — заставлять заказчика кликать лишнее.
 * Публикуется сразу, без модерации; закрывается, когда исполнитель
 * найден, — закрытая задача остаётся в кабинете, но уходит с витрины.
 */
class ItTaskController extends Controller
{
    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        $tasks = $company === null
            ? collect()
            : ItTask::query()
                ->where('company_id', $company->id)
                ->with(['contractor', 'threads.buyer'])
                ->withCount('files')
                ->orderByDesc('created_at')
                ->get();

        return Inertia::render('cabinet/it-tasks/Index', [
            'hasCompany' => $company !== null,
            'tasks' => $tasks->map(fn (ItTask $t): array => [
                'id' => $t->id,
                'slug' => $t->slug,
                'title' => $t->title,
                'service_type' => $t->serviceTypeLabel(),
                'budget' => $this->budgetLabel($t),
                'deadline' => DateHelper::dayMonthYear($t->deadline_at),
                'status' => $t->status,
                'status_label' => ItTask::STATUSES[$t->status] ?? $t->status,
                'responses' => $t->responses_count,
                'views' => $t->views_count,
                'files' => $t->files_count,
                'published' => DateHelper::dayMonthYear($t->published_at),
                'result_url' => $t->result_url,
                'result_summary' => $t->result_summary,
                'contractor' => $t->contractor?->name,
                'responders' => $t->threads->map(fn ($thread): array => [
                    'id' => $thread->buyer_company_id,
                    'name' => $thread->buyer?->name ?? 'Компания удалена',
                ])->values()->all(),
            ])->values(),
        ]);
    }

    public function create(Request $request): Response|RedirectResponse
    {
        if ($request->user()->company === null) {
            return redirect()->route('cabinet.company')
                ->with('warning', 'Сначала заполните данные компании — задача публикуется от её имени');
        }

        return Inertia::render('cabinet/it-tasks/Form', [
            'task' => null,
            'files' => [],
            'serviceTypes' => ItTask::SERVICE_TYPES,
            'currencies' => ItTask::CURRENCIES,
        ]);
    }

    public function store(Request $request): RedirectResponse
    {
        $company = $request->user()->company;
        abort_if($company === null, 404);

        $data = $this->validated($request);
        $files = $request->file('files', []);

        $task = ItTask::create([
            ...$data,
            'company_id' => $company->id,
            'user_id' => $request->user()->id,
            'status' => ItTask::STATUS_ACTIVE,
            'published_at' => now(),
        ]);

        $this->storeFiles($task, $files);

        return redirect()->route('cabinet.it-tasks')
            ->with('success', 'Задача опубликована в разделе «IT-услуги». Отклики исполнителей придут в чаты.');
    }

    public function edit(Request $request, int $id): Response
    {
        $task = $this->owned($request, $id);

        return Inertia::render('cabinet/it-tasks/Form', [
            'task' => [
                'id' => $task->id,
                'slug' => $task->slug,
                'title' => $task->title,
                'description' => $task->description,
                'service_type' => $task->service_type,
                'stack' => $task->stack ?? [],
                'budget_type' => $task->budget_type,
                'budget_from' => $task->budget_from !== null ? (float) $task->budget_from : null,
                'budget_to' => $task->budget_to !== null ? (float) $task->budget_to : null,
                'currency' => $task->currency,
                'deadline_at' => $task->deadline_at?->format('Y-m-d'),
                'status' => $task->status,
            ],
            'files' => $task->files->map(fn (ItTaskFile $f): array => [
                'id' => $f->id,
                'title' => $f->title,
                'size' => $f->sizeLabel(),
            ])->values(),
            'serviceTypes' => ItTask::SERVICE_TYPES,
            'currencies' => ItTask::CURRENCIES,
        ]);
    }

    public function update(Request $request, int $id): RedirectResponse
    {
        $task = $this->owned($request, $id);
        $data = $this->validated($request);

        $task->fill($data)->save();
        $this->storeFiles($task, $request->file('files', []));

        return redirect()->route('cabinet.it-tasks')->with('success', 'Задача обновлена');
    }

    /** Закрыть приём откликов: исполнитель найден или задача неактуальна. */
    public function close(Request $request, int $id): RedirectResponse
    {
        $task = $this->owned($request, $id);

        if ($task->isActive()) {
            $task->forceFill(['status' => ItTask::STATUS_CLOSED, 'closed_at' => now()])->save();
        }

        return back()->with('success', 'Задача закрыта — на витрине её больше нет, чаты остались');
    }

    /**
     * Отметить выполненной: результат и исполнитель.
     *
     * Исполнителя можно выбрать только из откликнувшихся — иначе поле
     * стало бы способом бесплатно «прикрепить» любую компанию.
     */
    public function complete(Request $request, int $id): RedirectResponse
    {
        $task = $this->owned($request, $id);

        $responders = $task->threads()->pluck('buyer_company_id')->all();

        $data = $request->validate([
            'result_url' => ['nullable', 'url', 'max:255'],
            'result_summary' => ['nullable', 'string', 'max:600'],
            'contractor_company_id' => ['nullable', 'integer', Rule::in($responders)],
        ], [
            'result_url.url' => 'Ссылка должна начинаться с http:// или https://',
            'contractor_company_id.in' => 'Исполнителем можно отметить только компанию, которая откликалась на задачу',
        ]);

        $task->forceFill([
            'status' => ItTask::STATUS_COMPLETED,
            'completed_at' => now(),
            'closed_at' => $task->closed_at ?? now(),
            'result_url' => $data['result_url'] ?? null,
            'result_summary' => $data['result_summary'] ?? null,
            'contractor_company_id' => $data['contractor_company_id'] ?? null,
        ])->save();

        return back()->with('success', 'Задача отмечена выполненной — она попала в «Выполненные» на витрине');
    }

    /** Открыть заново: снова на витрину, срок не трогаем. */
    public function reopen(Request $request, int $id): RedirectResponse
    {
        $task = $this->owned($request, $id);

        if (! $task->isActive()) {
            $task->forceFill(['status' => ItTask::STATUS_ACTIVE, 'closed_at' => null, 'published_at' => now()])->save();
        }

        return back()->with('success', 'Задача снова открыта для откликов');
    }

    public function destroy(Request $request, int $id): RedirectResponse
    {
        $task = $this->owned($request, $id);

        foreach ($task->files as $file) {
            Storage::disk('local')->delete($file->file_path);
        }

        $task->delete();

        return redirect()->route('cabinet.it-tasks')->with('success', 'Задача удалена');
    }

    public function destroyFile(Request $request, int $id, int $fileId): RedirectResponse
    {
        $task = $this->owned($request, $id);
        $file = $task->files()->findOrFail($fileId);

        Storage::disk('local')->delete($file->file_path);
        $file->delete();

        return back()->with('success', 'Файл удалён');
    }

    // ── Внутреннее ───────────────────────────────────────────

    /** @return array<string, mixed> */
    private function validated(Request $request): array
    {
        $data = $request->validate([
            'title' => ['required', 'string', 'min:10', 'max:120'],
            'description' => ['required', 'string', 'min:30', 'max:8000'],
            'service_type' => ['required', Rule::in(array_keys(ItTask::SERVICE_TYPES))],
            'stack' => ['nullable', 'array', 'max:'.ItTask::MAX_STACK],
            'stack.*' => ['string', 'max:30'],
            'budget_type' => ['required', Rule::in(ItTask::BUDGET_TYPES)],
            'budget_from' => ['nullable', 'numeric', 'min:0', 'max:99999999999', 'required_if:budget_type,fixed,range'],
            'budget_to' => ['nullable', 'numeric', 'min:0', 'max:99999999999', 'required_if:budget_type,range', 'gte:budget_from'],
            'currency' => ['required', Rule::in(ItTask::CURRENCIES)],
            'deadline_at' => ['nullable', 'date', 'after:today'],
            'files' => ['nullable', 'array', 'max:'.ItTaskFile::MAX_FILES],
            'files.*' => ['file', 'mimes:'.implode(',', ItTaskFile::ALLOWED_MIMES), 'max:'.ItTaskFile::MAX_SIZE_KB],
        ], [
            'title.required' => 'Назовите задачу — по названию её найдут исполнители',
            'title.min' => 'Название слишком короткое — опишите суть хотя бы в нескольких словах',
            'description.required' => 'Опишите задачу: что нужно сделать и что должно получиться',
            'description.min' => 'Описание слишком короткое — исполнителю нужно понять объём работы',
            'budget_from.required_if' => 'Укажите бюджет или выберите «договорной»',
            'budget_to.required_if' => 'Укажите верхнюю границу диапазона',
            'budget_to.gte' => 'Верхняя граница не может быть меньше нижней',
            'deadline_at.after' => 'Срок должен быть в будущем',
            'files.max' => 'Не больше '.ItTaskFile::MAX_FILES.' файлов к задаче',
            'files.*.mimes' => 'Допустимы PDF, документы Word и Excel, презентации, изображения, TXT и ZIP',
            'files.*.max' => 'Файл больше 20 МБ',
        ]);

        // Стек — чистые непустые строки без дублей
        $data['stack'] = array_values(array_unique(array_filter(array_map(
            fn ($tag): string => trim((string) $tag),
            $data['stack'] ?? [],
        ))));

        if ($data['budget_type'] === 'negotiable') {
            $data['budget_from'] = null;
            $data['budget_to'] = null;
        } elseif ($data['budget_type'] === 'fixed') {
            $data['budget_to'] = null;
        }

        unset($data['files']);

        return $data;
    }

    /** @param list<UploadedFile> $files */
    private function storeFiles(ItTask $task, array $files): void
    {
        $room = ItTaskFile::MAX_FILES - $task->files()->count();

        foreach (array_slice($files, 0, max(0, $room)) as $file) {
            if (! $file instanceof UploadedFile || ! $file->isValid()) {
                continue;
            }

            $path = $file->store("it-tasks/{$task->id}", 'local');

            if ($path === false) {
                continue;
            }

            $task->files()->create([
                'title' => mb_substr($file->getClientOriginalName(), 0, 190),
                'file_path' => $path,
                'file_size' => $file->getSize() ?: 0,
                'mime' => mb_substr((string) $file->getClientMimeType(), 0, 255),
            ]);
        }
    }

    private function owned(Request $request, int $id): ItTask
    {
        $company = $request->user()->company;
        abort_if($company === null, 404);

        // 404, а не 403: чужая задача не должна подтверждать своё существование
        return ItTask::query()
            ->with('files')
            ->where('company_id', $company->id)
            ->findOrFail($id);
    }

    private function budgetLabel(ItTask $task): string
    {
        $currency = $task->currency === 'UZS' ? 'сум' : $task->currency;
        $fmt = fn (float $v): string => number_format($v, 0, ',', ' ');

        return match ($task->budget_type) {
            'fixed' => $task->budget_from !== null ? $fmt((float) $task->budget_from).' '.$currency : 'договорной',
            'range' => $task->budget_from !== null && $task->budget_to !== null
                ? $fmt((float) $task->budget_from).' – '.$fmt((float) $task->budget_to).' '.$currency
                : 'договорной',
            default => 'договорной',
        };
    }
}
