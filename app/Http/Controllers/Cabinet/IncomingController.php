<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\AudienceView;
use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Listing;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Кто мной интересуется — компании, открывшие наши контакты,
 * и компании, смотревшие наши объявления и визитку.
 *
 * Названия видны только на Business и Premium (§3 ТЗ). На младших
 * тарифах показываются город и тип компании: сам факт интереса —
 * достаточный повод задуматься о тарифе, а имена уже платная часть.
 */
class IncomingController extends Controller
{
    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/Incoming', [
                'rows' => [],
                'viewers' => [],
                'sees_names' => false,
                'plan' => null,
            ]);
        }

        $plan = $company->plan();
        $seesNames = (bool) $plan->sees_interested_names;

        $rows = $company->unlockedBy()
            ->with(['company.city.translations', 'listing'])
            ->where('created_at', '>=', now()->subDays(30))
            ->latest()
            ->get()
            ->map(fn (ContactUnlock $u): array => [
                'id' => $u->id,
                // Скрытие делается на сервере: отдать имя и спрятать
                // его в вёрстке значит отдать его совсем. Рейтинг
                // и уровень проверки скрываются вместе с именем: по
                // точному рейтингу компания находится в открытом
                // каталоге и без имени
                'name' => $seesNames ? $u->company?->name : null,
                'slug' => $seesNames ? $u->company?->slug : null,
                'initials' => $seesNames ? $u->company?->initials() : null,
                'verified' => $seesNames ? (int) ($u->company?->verification_level ?? 0) : 0,
                'type' => $u->company?->primary_role === 'buyer' ? 'закупщик' : 'поставщик',
                'rating' => $seesNames ? (float) ($u->company?->rating ?? 0) : 0.0,
                'city' => $u->company?->city?->name() ?? 'Не указан',
                'listing' => $u->listing?->title,
                'when' => $u->created_at->diffForHumans(),
            ]);

        return Inertia::render('cabinet/Incoming', [
            'rows' => $rows,
            'viewers' => $this->viewers($company, $seesNames),
            'sees_names' => $seesNames,
            'plan' => ['name' => $plan->name],
        ]);
    }

    /**
     * Кто смотрел компанию: просмотры объявлений и визитки за месяц,
     * свёрнутые по зрителю. Правило видимости имён то же, что
     * и у открывших контакты, — скрытие делается на сервере.
     *
     * Свёртка считается базой, а не PHP: выборка «последние N строк,
     * потом группировка» занижала бы счётчики и теряла зрителей,
     * как только событий за месяц становится больше потолка. Потолок
     * здесь ограничивает список ЗРИТЕЛЕЙ — их цифры точны при любом
     * объёме событий.
     *
     * @return list<array<string, mixed>>
     */
    private function viewers(Company $company, bool $seesNames): array
    {
        $since = now()->subDays(30);

        $aggregates = AudienceView::query()
            ->where('target_company_id', $company->id)
            ->where('created_at', '>=', $since)
            ->selectRaw('viewer_company_id, count(*) as views_total, max(created_at) as last_at')
            ->groupBy('viewer_company_id')
            ->orderByDesc('last_at')
            ->limit(50)
            ->get();

        if ($aggregates->isEmpty()) {
            return [];
        }

        $viewerIds = $aggregates->pluck('viewer_company_id');

        // Только нужные колонки: у компаний и объявлений тяжёлые
        // описания, а разделу нужны имя, город да рейтинг
        $viewerCompanies = Company::query()
            ->whereIn('id', $viewerIds)
            ->with('city.translations')
            ->get(['id', 'name', 'slug', 'verification_level', 'primary_role', 'rating', 'city_id'])
            ->keyBy('id');

        $pages = AudienceView::query()
            ->where('target_company_id', $company->id)
            ->where('created_at', '>=', $since)
            ->whereIn('viewer_company_id', $viewerIds)
            ->select('viewer_company_id', 'listing_id')
            ->distinct()
            ->get()
            ->groupBy('viewer_company_id');

        // withTrashed: снятое с публикации объявление в истории
        // просмотров должно остаться под своим названием, а не
        // пропасть из подписи, оставив голый счётчик
        $titles = Listing::query()
            ->withTrashed()
            ->whereIn('id', $pages->flatten(1)->pluck('listing_id')->filter()->unique())
            ->pluck('title', 'id');

        return $aggregates
            ->map(function ($row, int $i) use ($viewerCompanies, $pages, $titles, $seesNames): array {
                $viewer = $viewerCompanies->get($row->viewer_company_id);
                $viewed = $pages->get($row->viewer_company_id) ?? collect();

                $listingTitles = $viewed->pluck('listing_id')->filter()
                    ->map(fn ($id) => $titles->get($id))
                    ->filter()->unique()->values();

                $looked = $listingTitles->take(2)->all();

                if ($listingTitles->count() > 2) {
                    $looked[] = 'ещё '.($listingTitles->count() - 2);
                }

                if ($viewed->contains(fn ($v): bool => $v->listing_id === null)) {
                    $looked[] = 'визитка компании';
                }

                return [
                    // Порядковый номер, а не id компании: числовой id
                    // зрителя на бесплатном тарифе — тоже утечка
                    'id' => $i,
                    'name' => $seesNames ? $viewer?->name : null,
                    'slug' => $seesNames ? $viewer?->slug : null,
                    'initials' => $seesNames ? $viewer?->initials() : null,
                    'verified' => $seesNames ? (int) ($viewer?->verification_level ?? 0) : 0,
                    'type' => $viewer?->primary_role === 'buyer' ? 'закупщик' : 'поставщик',
                    'rating' => $seesNames ? (float) ($viewer?->rating ?? 0) : 0.0,
                    'city' => $viewer?->city?->name() ?? 'Не указан',
                    'looked' => implode(' · ', $looked),
                    'views' => (int) $row->views_total,
                    'when' => Carbon::parse($row->last_at)->diffForHumans(),
                ];
            })
            ->values()
            ->all();
    }
}
