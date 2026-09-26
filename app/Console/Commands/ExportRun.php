<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Support\DatabaseExports;
use Illuminate\Console\Command;

/**
 * Выгрузка «как из админки», но сразу, без очереди.
 *
 * Тот же путь, что у кнопки: папка на постоянном диске, PHP-выгрузка,
 * теневая Python-выгрузка со сверкой, итог в run.json. Нужна для Shell
 * на Render и для проверки собранного образа в CI.
 */
class ExportRun extends Command
{
    protected $signature = 'savdex:export-run';

    protected $description = 'Выгрузить базу в Excel тем же путём, что кнопка в админке, и показать итог';

    public function handle(DatabaseExports $exports): int
    {
        // Без очереди: выгрузка выполняется здесь же. Задача в очереди
        // выполнила бы её второй раз
        $id = $exports->create(null);

        if ($id === null) {
            $this->error('Выгрузка уже идёт — дождитесь её в админке.');

            return self::FAILURE;
        }

        $exports->run($id);

        $run = $exports->find($id) ?? [];

        $this->line('Выгрузка: '.$id);
        $this->line('Итог: '.($run['status'] ?? '?'));
        $this->line('Файлы: '.implode(', ', $run['php']['files'] ?? []));

        $python = $run['python'] ?? [];
        $this->line('Сверка с Python: '.($python['status'] ?? '?').(isset($python['note']) ? ' — '.$python['note'] : ''));

        foreach (array_slice($python['problems'] ?? [], 0, 10) as $problem) {
            $this->line('  '.$problem);
        }

        return ($run['status'] ?? '') === DatabaseExports::DONE ? self::SUCCESS : self::FAILURE;
    }
}
