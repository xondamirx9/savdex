<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\Plan;
use Illuminate\Database\Seeder;

/**
 * Тарифы из §3 ТЗ и страницы /pricing.
 *
 * Цены в долларах: пересчёт в сумы идёт по курсу ЦБ. Free стоит ноль
 * и обязан существовать всегда — на него опирается расчёт лимитов
 * для компаний без подписки.
 */
class PlanSeeder extends Seeder
{
    public function run(): void
    {
        $plans = [
            [
                'code' => 'free',
                'listing_days' => 30,
                'name' => 'Free',
                'price_usd' => 0,
                'listings_limit' => 4,
                'contacts_limit' => 3,
                'responses_limit' => 0,
                'promo_units' => 0,
                'verification_days' => 5,
                'advanced_analytics' => false,
                'sees_interested_names' => false,
                'has_microsite' => false,
                'sort' => 1,
            ],
            [
                'code' => 'flash',
                'listing_days' => 30,
                'name' => 'Flash',
                'price_usd' => 40,
                'listings_limit' => 10,
                'contacts_limit' => 10,
                'responses_limit' => 20,
                'promo_units' => 5,
                'verification_days' => 3,
                'advanced_analytics' => false,
                'sees_interested_names' => false,
                'has_microsite' => false,
                'sort' => 2,
            ],
            [
                'code' => 'business',
                'listing_days' => 90,
                'name' => 'Business',
                'price_usd' => 80,
                'listings_limit' => 20,
                'contacts_limit' => 20,
                'responses_limit' => 40,
                'promo_units' => 50,
                'verification_days' => 1,
                'advanced_analytics' => true,
                'sees_interested_names' => true,
                'has_microsite' => true,
                'sort' => 3,
            ],
            [
                'code' => 'premium',
                'listing_days' => 180,
                'name' => 'Premium',
                'price_usd' => 150,
                'listings_limit' => 50,
                'contacts_limit' => 50,
                'responses_limit' => 60,
                'promo_units' => 150,
                'verification_days' => 1,
                'advanced_analytics' => true,
                'sees_interested_names' => true,
                'has_microsite' => true,
                'sort' => 4,
            ],
            [
                'code' => 'vip',
                'listing_days' => 365,
                'name' => 'VIP',
                'price_usd' => 250,
                'listings_limit' => null,   // null — без ограничений
                'contacts_limit' => null,
                'responses_limit' => null,
                'promo_units' => 300,
                'verification_days' => 1,
                'advanced_analytics' => true,
                'sees_interested_names' => true,
                'has_microsite' => true,
                'sort' => 5,
            ],
        ];

        foreach ($plans as $plan) {
            Plan::updateOrCreate(['code' => $plan['code']], $plan);
        }
    }
}
