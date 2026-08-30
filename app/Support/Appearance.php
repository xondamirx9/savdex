<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Setting;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Storage;

/**
 * Оформление витрины, задаваемое из админки.
 *
 * Пока это одна настройка — фон первого экрана главной. Вынесено
 * отдельным классом, а не строкой в контроллере: картинку кладут
 * через админку в хранилище, а витрине нужен публичный адрес,
 * и превращение одного в другое должно жить в одном месте.
 */
class Appearance
{
    public const KEY_HERO = 'hero_image';

    /** Картинка из коробки: её видно, пока свою не загрузили. */
    public const HERO_FALLBACK = '/images/hero-port.svg';

    /**
     * Адрес фона первого экрана.
     *
     * Пустая настройка возвращает картинку из коробки, а не null:
     * первый экран без фона — тёмный прямоугольник, и это выглядит
     * как поломка, а не как «фон не выбран».
     */
    public static function heroImage(): string
    {
        $path = trim((string) Setting::get(self::KEY_HERO, ''));

        if ($path === '') {
            return self::HERO_FALLBACK;
        }

        // Загруженный через админку файл лежит на публичном диске;
        // абсолютный адрес и внешняя ссылка берутся как есть
        if (str_starts_with($path, 'http://') || str_starts_with($path, 'https://') || str_starts_with($path, '/')) {
            return $path;
        }

        return Storage::disk('public')->url($path);
    }

    /**
     * Пропорции загруженного фона (ширина / высота).
     *
     * Первый экран подстраивает свою высоту под кадр: cover резал бы
     * верх и низ фотографии любой другой пропорции, а раскладка
     * по ширине оставляла бы синее поле под кадром. null — фон
     * не загружен (или это не растровый файл), пропорцию не знаем.
     */
    public static function heroImageRatio(): ?float
    {
        $path = trim((string) Setting::get(self::KEY_HERO, ''));

        if ($path === ''
            || str_starts_with($path, 'http://') || str_starts_with($path, 'https://') || str_starts_with($path, '/')
            || ! Storage::disk('public')->exists($path)) {
            return null;
        }

        // Кэш по имени файла: загрузка кладёт файл под новым именем,
        // и устаревшая пропорция отвалится сама
        return Cache::remember('hero_image_ratio:'.md5($path), now()->addDay(), function () use ($path): ?float {
            $info = @getimagesizefromstring((string) Storage::disk('public')->get($path));

            return $info !== false && $info[1] > 0 ? round($info[0] / $info[1], 4) : null;
        });
    }
}
