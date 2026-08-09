<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\Listing;
use App\Support\CabinetMetrics;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Дашборд кабинета.
 *
 * Показатели считаются на сервере: лимиты тарифа и остаток кредитов —
 * предмет биллинга, доверять их вычисление браузеру нельзя.
 */
class DashboardController extends Controller
{
    public function __invoke(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/Dashboard', [
                'company' => null,
                'metrics' => null,
                'series' => null,
                'events' => [],
                'limits' => null,
                'plan' => null,
            ]);
        }

        $metrics = new CabinetMetrics($company);
        $plan = $company->plan();
        $wallet = $company->wallet;
        $subscription = $company->subscription;

        return Inertia::render('cabinet/Dashboard', [
            'company' => [
                'name' => $company->name,
                'slug' => $company->slug,
                'completeness' => $company->profileCompleteness(),
                'missing' => $company->missingProfileFields(),
            ],
            'metrics' => $metrics->summary(),
            'series' => $metrics->series(),

            'events' => $company->events()->limit(5)->get()
                ->map(fn ($e): array => [
                    'id' => $e->id,
                    'type' => $e->type,
                    'tone' => $e->tone,
                    'message' => $e->message,
                    'url' => $e->url,
                    'ago' => $e->created_at->diffForHumans(),
                ]),

            'limits' => [
                'listings' => [
                    'used' => $company->activeListings()->count(),
                    'total' => $plan->listings_limit,
                ],
                'contacts' => [
                    'used' => $wallet?->contacts_used_this_period ?? 0,
                    'total' => $plan->contacts_limit,
                ],
                'promo' => [
                    'used' => max(0, $plan->promo_units - ($wallet?->promo_units ?? 0)),
                    'total' => $plan->promo_units,
                ],
                'resets_at' => $wallet?->period_resets_at?->translatedFormat('d.m.Y'),
            ],

            'plan' => [
                'name' => $plan->name,
                'until' => $subscription?->ends_at?->translatedFormat('d.m.Y'),
            ],

            'expiring' => $company->activeListings()
                ->whereNotNull('expires_at')
                ->where('expires_at', '<=', now()->addDays(7))
                ->count(),

            'drafts' => $company->listings()->where('status', Listing::STATUS_DRAFT)->count(),
        ]);
    }
}
