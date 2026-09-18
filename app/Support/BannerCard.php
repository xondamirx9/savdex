<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Banner;
use Illuminate\Support\Facades\Storage;

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
            'image' => Storage::disk('public')->url($banner->imageFor($locale)),
            'imageMobile' => $mobile !== null ? Storage::disk('public')->url($mobile) : null,
            'focal' => $banner->focal_x.'% '.$banner->focal_y.'%',
            'dismissible' => $banner->is_dismissible,
            'dismissDays' => Banner::DISMISS_DAYS,
        ];
    }
}
