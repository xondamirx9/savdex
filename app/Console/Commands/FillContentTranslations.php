<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Services\MachineTranslator;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Перевод текстов, которые страницы поставили в очередь
 * (см. App\Support\ContentTranslation).
 *
 * Запускается планировщиком каждую минуту небольшими порциями.
 * Вручную — `php artisan translations:fill --all`, чтобы перевести
 * всё накопившееся разом.
 */
class FillContentTranslations extends Command
{
    /** После стольких неудач текст больше не пробуем. */
    public const MAX_ATTEMPTS = 5;

    protected $signature = 'translations:fill
        {--limit=40 : Сколько текстов перевести за проход}
        {--all : Переводить, пока очередь не опустеет}';

    protected $description = 'Перевести тексты из базы, поставленные страницами в очередь';

    public function handle(MachineTranslator $translator): int
    {
        if (! config('services.machine_translation.enabled')) {
            $this->warn('Машинный перевод выключен (MACHINE_TRANSLATION_ENABLED).');

            return self::SUCCESS;
        }

        $limit = max(1, (int) $this->option('limit'));
        $done = 0;
        $failed = 0;

        do {
            $rows = DB::table('content_translations')
                ->whereNull('translation')
                ->where('attempts', '<', self::MAX_ATTEMPTS)
                ->orderBy('attempts')
                ->orderBy('id')
                ->limit($limit)
                ->get(['id', 'locale', 'source', 'attempts']);

            foreach ($rows as $row) {
                $translated = $translator->translate((string) $row->source, (string) $row->locale);

                // Переводчик просит подождать: попытку не списываем,
                // проход прекращаем — продолжит следующий
                if ($translated === null && $translator->wasRateLimited()) {
                    $this->warn('Переводчик ограничил частоту запросов — продолжим позже.');

                    break 2;
                }

                DB::table('content_translations')->where('id', $row->id)->update(
                    $translated !== null
                        ? ['translation' => $translated, 'updated_at' => now()]
                        : ['attempts' => $row->attempts + 1, 'updated_at' => now()],
                );

                $translated !== null ? $done++ : $failed++;
            }
        } while ($this->option('all') && $rows->count() === $limit);

        $this->info("Переведено: {$done}, не удалось: {$failed}.");

        return self::SUCCESS;
    }
}
