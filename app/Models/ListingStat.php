<?php

declare(strict_types=1);

namespace App\Models;

use Database\Factories\ListingStatFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Статистика объявления за день.
 * Хранится по дням, а не счётчиком: аналитика сравнивает периоды.
 */
#[Fillable(['listing_id', 'date', 'impressions', 'views', 'favorites', 'unlocks'])]
class ListingStat extends Model
{
    /** @use HasFactory<ListingStatFactory> */
    use HasFactory;

    protected function casts(): array
    {
        return ['date' => 'date'];
    }

    public function listing(): BelongsTo
    {
        return $this->belongsTo(Listing::class);
    }
}
