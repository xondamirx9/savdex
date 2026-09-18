<?php

declare(strict_types=1);

namespace App\Models;

use App\Support\ImageStore;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Картинка баннера под отдельный язык. */
#[Fillable(['banner_id', 'locale', 'image_path', 'image_mobile_path'])]
class BannerImage extends Model
{
    /**
     * Убранный из формы язык уносит с собой свои файлы.
     *
     * Та же причина, что у баннера: диск постоянный, а строку,
     * удалённую из списка языков, уже никто не вспомнит.
     */
    protected static function booted(): void
    {
        static::updating(function (self $image): void {
            $store = app(ImageStore::class);

            foreach (['image_path', 'image_mobile_path'] as $column) {
                if ($image->isDirty($column)) {
                    $store->delete($image->getOriginal($column));
                }
            }
        });

        static::deleting(fn (self $image) => app(ImageStore::class)
            ->delete($image->image_path, $image->image_mobile_path));
    }

    public function banner(): BelongsTo
    {
        return $this->belongsTo(Banner::class);
    }
}
