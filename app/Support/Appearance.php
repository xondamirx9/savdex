<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Setting;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Storage;

/**
 * Оформление витрины, задаваемое из админки: фон первого экрана
 * и логотип площадки.
 *
 * Вынесено отдельным классом, а не строками в контроллерах:
 * картинку кладут через админку в хранилище, а витрине нужен
 * публичный адрес, и превращение одного в другое должно жить
 * в одном месте — логотип читают шапка, подвал, фавикон и админка.
 */
class Appearance
{
    public const KEY_HERO = 'hero_image';

    public const KEY_LOGO = 'logo_image';

    /** Картинка из коробки: её видно, пока свою не загрузили. */
    public const HERO_FALLBACK = '/images/hero-port.svg';

    /** Знак из коробки: он же лежит в репозитории с самого начала. */
    public const LOGO_FALLBACK = '/images/logo-mark.svg';

    /** Иконка для экрана «Домой»: растр, которого требует iOS. */
    public const TOUCH_FALLBACK = '/images/logo-touch.png';

    /** Подсказка под полем загрузки — она же пояснение к настройке. */
    public const LOGO_HINT = 'Знак в шапке, в подвале, на вкладке браузера и в админке. Квадратный, от 512 px; лучше SVG или PNG с прозрачным фоном — знак стоит и на белом, и на тёмно-синем. Пустое поле возвращает знак по умолчанию';

    /**
     * Адрес фона первого экрана.
     *
     * Пустая настройка возвращает картинку из коробки, а не null:
     * первый экран без фона — тёмный прямоугольник, и это выглядит
     * как поломка, а не как «фон не выбран».
     */
    public static function heroImage(): string
    {
        return self::url(self::KEY_HERO, self::HERO_FALLBACK);
    }

    /**
     * Адрес логотипа площадки.
     *
     * Пустая настройка возвращает знак из репозитория: шапка без
     * логотипа читается как недогрузившаяся страница.
     */
    public static function logo(): string
    {
        return self::url(self::KEY_LOGO, self::LOGO_FALLBACK);
    }

    /** Значение настройки логотипа — путь на публичном диске или пусто. */
    public static function logoPath(): string
    {
        return trim((string) Setting::get(self::KEY_LOGO, ''));
    }

    /**
     * Сохранить логотип.
     *
     * Строку заводит миграция, но полагаться на это нельзя: настройку
     * может удалить администратор — так уже случилось с фоном первого
     * экрана, и раздел «Оформление» тогда пропал из админки целиком.
     * Поэтому кнопка загрузки создаёт строку, если её нет, и площадка
     * не остаётся без способа сменить знак.
     *
     * Название и пояснение при этом не переписываются: их правят в той
     * же админке, и загрузка картинки не повод откатывать правку.
     */
    public static function setLogo(string $path): void
    {
        $setting = Setting::firstOrNew(['key' => self::KEY_LOGO]);

        if (! $setting->exists) {
            $setting->fill([
                'group' => 'appearance',
                'label' => 'Логотип площадки',
                'description' => self::LOGO_HINT,
                'type' => 'image',
                'sort' => 6,
            ]);
        }

        $setting->value = $path;
        $setting->save();

        Setting::flushCache();
    }

    /**
     * Тип логотипа для <link rel="icon">.
     *
     * Браузер выбирает иконку по type, не скачивая файл: с чужим
     * типом у SVG вкладка остаётся с пустым листом. У растра тип
     * не указываем вовсе — браузер определит его сам.
     */
    public static function logoType(): ?string
    {
        return str_ends_with(strtolower(self::logo()), '.svg') ? 'image/svg+xml' : null;
    }

    /**
     * Иконка для экрана «Домой» на телефоне.
     *
     * iOS понимает здесь только растр: SVG она молча игнорирует
     * и рисует уменьшенный снимок страницы. Поэтому загруженный
     * вектор сюда не идёт — остаётся готовая картинка из репозитория.
     */
    public static function touchIcon(): string
    {
        $logo = self::logo();

        return preg_match('/\.(png|jpe?g)$/i', $logo) === 1 ? $logo : self::TOUCH_FALLBACK;
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
            || self::isAbsolute($path)
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

    /** Значение настройки-картинки как публичный адрес. */
    private static function url(string $key, string $fallback): string
    {
        $path = trim((string) Setting::get($key, ''));

        if ($path === '') {
            return $fallback;
        }

        // Загруженный через админку файл лежит на публичном диске;
        // абсолютный адрес и внешняя ссылка берутся как есть
        return self::isAbsolute($path) ? $path : Storage::disk('public')->url($path);
    }

    private static function isAbsolute(string $path): bool
    {
        return str_starts_with($path, 'http://')
            || str_starts_with($path, 'https://')
            || str_starts_with($path, '/');
    }
}
