<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\CompanyDocument;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;
use Symfony\Component\HttpFoundation\StreamedResponse;

/**
 * Файлы компании: документы для верификации и материалы для партнёров.
 *
 * Хранятся в приватном диске и отдаются через контроллер, а не по
 * прямой ссылке: у документов есть модерация и флаг публичности,
 * и файл в public/ обошёл бы обе проверки — достаточно угадать имя.
 */
class CompanyFileController extends Controller
{
    public function store(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null) {
            return back()->with('error', 'Сначала заполните данные компании');
        }

        $types = array_keys([...CompanyDocument::VERIFICATION_TYPES, ...CompanyDocument::MATERIAL_TYPES]);

        $data = $request->validate([
            'type' => ['required', 'in:'.implode(',', $types)],
            'title' => ['required', 'string', 'max:190'],
            'file' => [
                'required', 'file',
                'mimes:'.implode(',', CompanyDocument::ALLOWED_MIMES),
                'max:'.CompanyDocument::MAX_SIZE_KB,
            ],
            'valid_until' => ['nullable', 'date', 'after:today'],
            'is_public' => ['boolean'],
        ], [
            'title.required' => 'Назовите файл — партнёр увидит именно это название',
            'file.required' => 'Выберите файл',
            'file.mimes' => 'Допустимы PDF, документы Word и Excel, презентации, изображения и ZIP',
            'file.max' => 'Файл больше 20 МБ. Сожмите его или разбейте на части',
            'valid_until.after' => 'Срок действия уже истёк — такой документ не подтверждает ничего',
        ]);

        $file = $request->file('file');

        // Имя из хеша: оригинальное может содержать что угодно, включая
        // пути и кириллицу, а совпадение имён у разных компаний перезапишет файл
        $path = $file->store("companies/{$company->id}/documents", 'local');

        $document = CompanyDocument::create([
            'company_id' => $company->id,
            'type' => $data['type'],
            'title' => $data['title'],
            'file_path' => $path,
            'file_size' => $file->getSize(),
            'mime' => $file->getClientMimeType(),
            'valid_until' => $data['valid_until'] ?? null,
            'is_public' => $request->boolean('is_public', true),
            // Материалам модерация не нужна: это не подтверждение статуса
            'moderation_status' => array_key_exists($data['type'], CompanyDocument::MATERIAL_TYPES)
                ? CompanyDocument::STATUS_APPROVED
                : CompanyDocument::STATUS_PENDING,
        ]);

        return back()->with('success', $document->isMaterial()
            ? 'Файл загружен и виден партнёрам на визитке'
            : 'Документ загружен и отправлен на проверку');
    }

    /** Переключение показа на визитке. */
    public function update(Request $request, int $id): RedirectResponse
    {
        $document = $this->owned($request, $id);

        $document->forceFill([
            'is_public' => $request->boolean('is_public'),
        ])->save();

        return back()->with('success', $document->is_public
            ? 'Файл показывается на визитке'
            : 'Файл скрыт с визитки');
    }

    public function destroy(Request $request, int $id): RedirectResponse
    {
        $document = $this->owned($request, $id);

        Storage::disk('local')->delete($document->file_path);
        $document->delete();

        return back()->with('success', 'Файл удалён');
    }

    /**
     * Скачивание.
     *
     * Проверка доступа обязательна: приватный файл отдаётся только
     * своим сотрудникам, публичный — всем, но лишь когда он реально
     * помечен к показу и прошёл модерацию.
     */
    public function download(Request $request, int $id): StreamedResponse
    {
        $document = CompanyDocument::find($id);

        abort_if($document === null, 404);

        $isOwn = $request->user()?->company_id === $document->company_id;

        abort_unless($isOwn || $document->isVisibleOnCard(), 404);

        abort_unless(Storage::disk('local')->exists($document->file_path), 404);

        /*
         * Имя для скачивания — человеческое: хеш в имени файла на диске
         * нужен нам, а не тому, кто его открывает.
         *
         * Слэши и точки в начале вырезаются: название задаёт пользователь,
         * а Content-Disposition их не принимает — Symfony бросает
         * исключение, и человек получал 500 на скачивании своего же файла.
         */
        $extension = pathinfo($document->file_path, PATHINFO_EXTENSION);

        $name = trim(preg_replace('#[/\\\\]+#', '-', $document->title) ?? '', ' .-');

        return Storage::disk('local')->download(
            $document->file_path,
            ($name !== '' ? $name : 'file').'.'.$extension,
        );
    }

    private function owned(Request $request, int $id): CompanyDocument
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $document = $company->documents()->find($id);

        abort_if($document === null, 404);

        return $document;
    }
}
