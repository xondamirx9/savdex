<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Фотография объявления.
 *
 * Первая по порядку служит обложкой — отдельного флага нет: «сделать
 * обложкой» и «поставить первой» одно и то же, а два способа сказать
 * одно приводят к рассинхрону.
 */
#[Fillable(['listing_id', 'path', 'thumb_path', 'sort'])]
class ListingImage extends Model
{
    /** Публичный адрес полного изображения. */
    public function url(): string
    {
        return asset('storage/'.$this->path);
    }

    /** Адрес уменьшенной копии; для старых записей — полное изображение. */
    public function thumbUrl(): string
    {
        return asset('storage/'.($this->thumb_path ?? $this->path));
    }

    public function listing(): BelongsTo
    {
        return $this->belongsTo(Listing::class);
    }
}
