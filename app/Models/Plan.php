<?php

declare(strict_types=1);

namespace App\Models;

use App\Models\Concerns\RefusesDeletionWhenReferenced;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * Тариф.
 *
 * Цена задаётся в долларах и пересчитывается по курсу ЦБ — подход
 * InvestIn. При скачке курса не нужно править каждый тариф вручную.
 * price_uzs перекрывает расчёт, когда витринную цену зафиксировали.
 *
 * С этапа 2 переноса тарифы правятся в разделе на Python
 * (python/savdex/billing/), и цены с лимитами задаёт админка:
 * PlanSeeder существующие не трогает.
 */
#[Fillable([
    'code', 'name', 'price_usd', 'price_uzs', 'period_days', 'listing_days',
    'listings_limit', 'contacts_limit', 'responses_limit', 'promo_units', 'verification_days',
    'advanced_analytics', 'sees_interested_names', 'has_microsite', 'sort', 'is_active',
])]
class Plan extends Model
{
    use RefusesDeletionWhenReferenced;

    public const FREE = 'free';

    /** Высший тариф: его объявления ведут ленту главной. */
    public const VIP = 'vip';

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

    /**
     * Что удерживает тариф от удаления.
     *
     * Промокоды на тариф уходили бы каскадом, у счетов обнулялся бы
     * тариф, а free и vip читает код — без них ломаются лимиты компаний
     * без подписки и лента главной.
     *
     * @return array<string, int>
     */
    public function references(): array
    {
        return array_filter([
            'код площадки' => in_array($this->code, [self::FREE, self::VIP], true) ? 1 : 0,
            'подписки' => $this->subscriptions()->count(),
            'счета' => Payment::query()->where('plan_id', $this->id)->count(),
            'промокоды' => PromoCode::query()->where('plan_id', $this->id)->count(),
        ]);
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
