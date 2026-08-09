<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Запущенное продвижение объявления.
 *
 * impressions_before фиксируется при запуске: эффект инструмента
 * нельзя честно посчитать задним числом — периоды накладываются.
 */
#[Fillable([
    'listing_id', 'company_id', 'promotion_type_id', 'category_id', 'units_spent',
    'status', 'starts_at', 'ends_at', 'impressions_before', 'impressions_after',
])]
class Promotion extends Model
{
    protected function casts(): array
    {
        return ['starts_at' => 'datetime', 'ends_at' => 'datetime'];
    }

    /**
     * active_key поддерживается моделью, а не заполняется вручную.
     *
     * Это опора уникального индекса «одно продвижение на объявление»:
     * у активной строки ключ заполнен, у завершённой — null, а NULL
     * в уникальном индексе не конфликтует ни с чем. Забыть обнулить
     * его при завершении значит навсегда занять место.
     */
    protected static function booted(): void
    {
        static::saving(function (self $promotion): void {
            $promotion->active_key = $promotion->status === 'active'
                ? $promotion->listing_id.':'.$promotion->promotion_type_id
                : null;
        });
    }

    public function listing(): BelongsTo
    {
        return $this->belongsTo(Listing::class);
    }

    public function type(): BelongsTo
    {
        return $this->belongsTo(PromotionType::class, 'promotion_type_id');
    }

    /**
     * Прирост показов в процентах.
     * null, пока продвижение идёт: промежуточная цифра вводит в заблуждение.
     */
    public function effect(): ?int
    {
        if ($this->impressions_after === null || $this->impressions_before < 1) {
            return null;
        }

        return (int) round(($this->impressions_after - $this->impressions_before) / $this->impressions_before * 100);
    }
}
