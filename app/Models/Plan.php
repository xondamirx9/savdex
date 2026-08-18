<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * Тариф.
 *
 * Цена задаётся в долларах и пересчитывается по курсу ЦБ — подход
 * InvestIn. При скачке курса не нужно править каждый тариф вручную.
 * price_uzs перекрывает расчёт, когда витринную цену зафиксировали.
 */
#[Fillable([
    'code', 'name', 'price_usd', 'price_uzs', 'period_days', 'listing_days',
    'listings_limit', 'contacts_limit', 'responses_limit', 'promo_units', 'verification_days',
    'advanced_analytics', 'sees_interested_names', 'has_microsite', 'sort', 'is_active',
])]
class Plan extends Model
{
    public const FREE = 'free';

    protected function casts(): array
    {
        return [
            'price_usd' => 'decimal:2',
            'advanced_analytics' => 'boolean',
            'sees_interested_names' => 'boolean',
            'has_microsite' => 'boolean',
            'is_active' => 'boolean',
        ];
    }

    public function subscriptions(): HasMany
    {
        return $this->hasMany(Subscription::class);
    }

    /**
     * Цена в сумах: зафиксированная либо пересчитанная по курсу.
     *
     * Округление до тысяч обязательно. Прямой пересчёт даёт «469 963 сум» —
     * цена, которую никто не назначал; она читается как ошибка расчёта,
     * а не как решение компании.
     */
    public function priceUzs(float $rate): int
    {
        if ($this->price_uzs !== null) {
            return $this->price_uzs;
        }

        return (int) (round((float) $this->price_usd * $rate / 1000) * 1000);
    }

    /** null в лимите означает «без ограничений», а не «ноль». */
    public function limitLabel(?int $limit): string
    {
        return $limit === null ? 'без ограничений' : (string) $limit;
    }
}
