<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\Cache;

/**
 * Настройка площадки: контакты, реквизиты, соцсети, тексты подвала.
 *
 * Значение хранится в json, чтобы одинаково класть строку, число,
 * флаг и список без отдельной колонки под каждый тип.
 */
#[Fillable(['group', 'key', 'label', 'description', 'type', 'value', 'sort'])]
class Setting extends Model
{
    /** Кэш на сутки: настройки читаются на каждой странице, меняются раз в месяц. */
    private const CACHE_KEY = 'settings.all';

    public const GROUPS = [
        'general' => 'Общие',
        'appearance' => 'Оформление',
        'contacts' => 'Контакты',
        'legal' => 'Реквизиты',
        'social' => 'Соцсети',
        'limits' => 'Ограничения',
        'moderation' => 'Модерация',
    ];

    protected function casts(): array
    {
        return ['value' => 'array'];
    }

    protected static function booted(): void
    {
        // Кэш сбрасывается при любом изменении: настройка, которая
        // применяется через сутки, воспринимается как несохранившаяся
        static::saved(fn () => self::flushCache());
        static::deleted(fn () => self::flushCache());
    }

    /**
     * Сброс кэша настроек.
     *
     * Модель делает это сама при сохранении. Метод нужен там, где
     * строки правятся в обход модели и события не срабатывают, —
     * прежде всего в миграциях, которые ходят в базу через DB::table.
     */
    public static function flushCache(): void
    {
        Cache::forget(self::CACHE_KEY);
    }

    /**
     * Все настройки одним массивом.
     *
     * Имя values, а не all: Model::all() — штатный метод Eloquent,
     * и его переопределение с другой сигнатурой ломает модель
     * в неожиданных местах.
     *
     * @return array<string, mixed>
     */
    public static function values(): array
    {
        return Cache::remember(
            self::CACHE_KEY,
            now()->addDay(),
            fn (): array => self::query()->pluck('value', 'key')->all(),
        );
    }

    public static function get(string $key, mixed $default = null): mixed
    {
        return self::values()[$key] ?? $default;
    }

    public static function put(string $key, mixed $value): void
    {
        self::query()->where('key', $key)->update(['value' => json_encode($value)]);

        Cache::forget(self::CACHE_KEY);
    }
}
