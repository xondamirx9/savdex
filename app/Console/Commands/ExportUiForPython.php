<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Support\Locales;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;

/**
 * Словарь интерфейса и «N минут назад» — для страниц, которые отдаёт
 * Django (этап 3 переноса).
 *
 * Страница на Django должна говорить теми же словами, что страница
 * Laravel: тот же словарь lang/<язык>/ui.php (поверх русского, как
 * HandleInertiaRequests::translations) и те же подписи колокольчика
 * («5 минут назад» — Carbon::diffForHumans со склонением под язык).
 * Словарь — PHP-массив, а склонения — правила Carbon; переписывать то
 * и другое на Python значит однажды разойтись. Поэтому Laravel сам
 * выгружает их в JSON, а Django читает готовое.
 *
 * Запускается при старте службы (docker/render-entrypoint.sh), до
 * Django; словарь меняется только с релизом.
 */
class ExportUiForPython extends Command
{
    protected $signature = 'savdex:export-ui';

    protected $description = 'Словарь и подписи «назад» для страниц на Django';

    /** Единицы Carbon и до скольких их считать: дальше — следующая единица. */
    private const UNITS = [
        'second' => 59,
        'minute' => 59,
        'hour' => 23,
        'day' => 6,
        'week' => 4,
        'month' => 11,
        'year' => 100,
    ];

    public static function directory(): string
    {
        return storage_path('app/python/ui');
    }

    public function handle(): int
    {
        File::ensureDirectoryExists(self::directory());

        /** @var array<string, mixed> $base */
        $base = trans('ui', locale: Locales::DEFAULT);

        foreach (Locales::codes() as $locale) {
            /** @var array<string, mixed> $active */
            $active = trans('ui', locale: $locale);

            $data = [
                'translations' => $locale === Locales::DEFAULT ? $active : array_replace_recursive($base, $active),
                'ago' => $this->ago($locale),
            ];

            $path = self::directory()."/{$locale}.json";
            // Сначала во временный файл: Django не должен прочитать
            // наполовину записанный словарь
            File::put($path.'.tmp', json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
            File::move($path.'.tmp', $path);
        }

        $this->info('Словарь выгружен: '.self::directory());

        return self::SUCCESS;
    }

    /**
     * «N единиц назад» для каждой единицы и числа — ровно то, что
     * вернул бы diffForHumans. Дата отсчитывается от одного момента,
     * так что календарь (длина месяца) на строку не влияет.
     *
     * @return array<string, array<int, string>>
     */
    private function ago(string $locale): array
    {
        $now = Carbon::create(2026, 1, 1, 0, 0, 0, 'UTC');
        $table = [];

        foreach (self::UNITS as $unit => $max) {
            for ($count = 1; $count <= $max; $count++) {
                $past = match ($unit) {
                    'week' => $now->copy()->subDays(7 * $count),
                    default => $now->copy()->sub($unit, $count),
                };

                $table[$unit][$count] = $past->locale($locale)->diffForHumans($now->copy(), ['syntax' => Carbon::DIFF_RELATIVE_TO_NOW]);
            }
        }

        return $table;
    }
}
