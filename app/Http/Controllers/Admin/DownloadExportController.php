<?php

declare(strict_types=1);

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Support\AdminAccess;
use App\Support\AdminLog;
use App\Support\DatabaseExports;
use Illuminate\Support\Facades\Storage;
use Symfony\Component\HttpFoundation\StreamedResponse;

/**
 * Скачивание книги выгрузки.
 *
 * Отдельным адресом за входом в админку, а не ответом Livewire: тот
 * передаёт файл целиком внутри JSON, а книга на живой базе — мегабайты.
 *
 * Каждое скачивание — строка в журнале действий. В файле персональные
 * данные всех пользователей, и вопрос «кто унёс базу» должен иметь
 * ответ.
 */
class DownloadExportController extends Controller
{
    public function __invoke(DatabaseExports $exports, string $run, string $file): StreamedResponse
    {
        abort_unless(AdminAccess::allows('backups.export'), 403);

        $path = $exports->bookPath($run, $file);

        // 404, а не 403: чужой или выдуманный путь не должен
        // подтверждать, что такой файл существует
        abort_if($path === null, 404);

        AdminLog::record('downloaded', 'backups', note: "Скачан файл выгрузки {$run}/{$file}");

        return Storage::disk('local')->download($path, $file);
    }
}
