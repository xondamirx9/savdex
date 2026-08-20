<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Setting;
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
}
