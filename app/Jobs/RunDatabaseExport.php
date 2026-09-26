<?php

declare(strict_types=1);

namespace App\Jobs;

use App\Support\DatabaseExports;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Throwable;

/**
 * Выгрузка базы в Excel — фоном, по кнопке в админке.
 *
 * В очереди, а не в запросе: выгрузка читает всю базу, а веб-процессы
 * Apache сосчитаны по памяти впритык (docker/render-entrypoint.sh) —
 * так площадка уже падала в сентябре. Воркер очереди один, его память
 * заложена в резерв.
 *
 * Одна попытка: повтор выгрузки, упавшей на середине, даёт вторую
 * такую же нагрузку ради того же файла. Человек увидит «ошибка»
 * и нажмёт кнопку сам, когда разберётся.
 *
 * $timeout задачи перекрывает --timeout воркера (60 с по умолчанию),
 * иначе воркер убил бы выгрузку большой базы на середине. retry_after
 * очереди (90 с) короче, но на Render воркер один: занятый выгрузкой,
 * он не возьмёт ту же задачу второй раз.
 */
class RunDatabaseExport implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable;

    public int $tries = 1;

    // PHP-выгрузка плюс теневая Python-выгрузка со сверкой
    public int $timeout = 900;

    public function __construct(public readonly string $runId) {}

    public function handle(DatabaseExports $exports): void
    {
        $exports->run($this->runId);
    }

    public function failed(Throwable $e): void
    {
        app(DatabaseExports::class)->markFailed($this->runId, $e->getMessage());
    }
}
