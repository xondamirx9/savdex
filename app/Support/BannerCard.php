<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Banner;

/**
 * Баннер в виде, пригодном для страницы.
 *
 * Отдельно от модели, как ListingCard и TenderCard: фронтенду нужны
 * готовые адреса картинок на языке страницы, а не связи и пути.
 */
final class BannerCard
{
    /**
     * Баннер места или null, если показывать нечего.
     *
     * @return array<string, mixed>|null
     */
    public static function forPlacement(string $placement): ?array
    {
        $banner = Banner::forPlacement($placement);

        if ($banner === null) {
            return null;
        }

        $locale = app()->getLocale();
        $mobile = $banner->mobileImageFor($locale);

        return [
            // Ключ закрытия: в нём номер баннера, чтобы закрытая
            // прошлая акция не прятала новую
            'key' => 'banner-'.$banner->id,
            'url' => $banner->url,
            'alt' => $banner->alt,
            /*
             * Адрес — через asset(), как у логотипов и обложек.
             *
             * Storage::url() собирает его из APP_URL, то есть из
             * настройки, а asset() — из адреса, по которому сайт
             * открыли. Логотипы на боевом сайте видны, значит их путь
             * проверен. Два разных способа для одной папки загрузок —
             * это однажды картинки одного вида есть, а другого нет.
             */
            'image' => asset('storage/'.$banner->imageFor($locale)),
            'imageMobile' => $mobile !== null ? asset('storage/'.$mobile) : null,
            'focal' => $banner->focal_x.'% '.$banner->focal_y.'%',
            'dismissible' => $banner->is_dismissible,
            'dismissDays' => Banner::DISMISS_DAYS,
        ];
    }
}
