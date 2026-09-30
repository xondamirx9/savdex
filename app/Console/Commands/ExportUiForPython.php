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
 * С шага 73 выгрузка лежит в самом коде Python (python/savdex/locale/ui,
 * `php artisan savdex:export-ui --to=python/savdex/locale/ui` после правки
 * lang/*): Django не нужен Laravel при старте. Что выгрузка не отстала от
 * lang/*, следит tests/Feature/ExportUiForPythonTest.
 */
class ExportUiForPython extends Command
{
    protected $signature = 'savdex:export-ui {--to= : Каталог вместо storage/app/python/ui — например, python/savdex/locale/ui}';

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
        $directory = $this->option('to') !== null && $this->option('to') !== ''
            ? base_path((string) $this->option('to'))
            : self::directory();

        File::ensureDirectoryExists($directory);

        /** @var array<string, mixed> $base */
        $base = trans('ui', locale: Locales::DEFAULT);

        foreach (Locales::codes() as $locale) {
            /** @var array<string, mixed> $active */
            $active = trans('ui', locale: $locale);

            $data = [
                'translations' => $locale === Locales::DEFAULT ? $active : array_replace_recursive($base, $active),
                'groups' => $this->groups($locale),
                'ago' => $this->ago($locale),
                'dates' => $this->dates($locale),
            ];

            $path = $directory."/{$locale}.json";
            // Сначала во временный файл: Django не должен прочитать
            // наполовину записанный словарь
            File::put($path.'.tmp', json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
            File::move($path.'.tmp', $path);
        }

        $this->info('Словарь выгружен: '.$directory);

        return self::SUCCESS;
    }

    /**
     * Словари, кроме ui, — те, что нужны страницам на Django (кабинет,
     * этап 5): __('company.field.tin') и подобные. Нет файла или ключа
     * на языке — русский, как у переводчика Laravel с запасным языком.
     *
     * @return array<string, array<string, mixed>>
     */
    private function groups(string $locale): array
    {
        $groups = [];

        foreach (['company', 'specs', 'validation'] as $group) {
            $base = trans($group, locale: Locales::DEFAULT);
            $active = trans($group, locale: $locale);

            $groups[$group] = array_replace_recursive(
                is_array($base) ? $base : [],
                is_array($active) ? $active : [],
            );
        }

        return $groups;
    }

    /**
     * «15 сентября 2026» — DateHelper::dayMonthYear на других языках идёт
     * через Carbon::isoFormat('D MMMM YYYY'): названия месяцев и порядок
     * слов у каждого языка свои. Шаблон на каждый месяц: {d} и {y} Django
     * подставит сам.
     *
     * @return array<string, array<int, string>>
     */
    private function dates(string $locale): array
    {
        $formats = ['day_month_year' => 'D MMMM YYYY', 'month_year' => 'MMMM YYYY'];
        $table = [];

        foreach ($formats as $name => $format) {
            for ($month = 1; $month <= 12; $month++) {
                $text = Carbon::create(2037, $month, 28, 12, 0, 0, 'UTC')->locale($locale)->isoFormat($format);
                $table[$name][$month] = str_replace(['2037', '28'], ['{y}', '{d}'], $text);
            }
        }

        return $table;
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

        /*
         * Язык — как на странице: через app()->setLocale, а не
         * ->locale() у даты. Для китайского они расходятся: страница
         * пишет «21 分钟前», а ->locale('zh') — «21分钟前», и Django
         * показывал бы подпись не такой, как Laravel.
         */
        $previous = app()->getLocale();
        app()->setLocale($locale);

        foreach (self::UNITS as $unit => $max) {
            for ($count = 1; $count <= $max; $count++) {
                $past = match ($unit) {
                    'week' => $now->copy()->subDays(7 * $count),
                    default => $now->copy()->sub($unit, $count),
                };

                $table[$unit][$count] = $past->diffForHumans($now->copy(), ['syntax' => Carbon::DIFF_RELATIVE_TO_NOW]);
            }
        }

        app()->setLocale($previous);

        return $table;
    }
}
