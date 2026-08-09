<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\Company;
use App\Models\Listing;
use App\Support\Notifier;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Мои объявления.
 *
 * Все действия проверяют владельца через ownedListing(): пользователь
 * не должен продлевать или снимать чужое объявление, даже если угадал id.
 */
class ListingController extends Controller
{
    /** Вкладки статусов — порядок как в интерфейсе. */
    private const TABS = [
        Listing::STATUS_ACTIVE => 'Активные',
        Listing::STATUS_MODERATION => 'На модерации',
        Listing::STATUS_DRAFT => 'Черновики',
        Listing::STATUS_EXPIRED => 'Истёкшие',
        Listing::STATUS_REJECTED => 'Отклонённые',
    ];

    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/listings/Index', [
                'listings' => [],
                'counts' => array_map(fn () => 0, self::TABS),
                'tabs' => self::TABS,
                'status' => Listing::STATUS_ACTIVE,
                'limit' => null,
            ]);
        }

        $status = $request->string('status')->toString();

        if (! array_key_exists($status, self::TABS)) {
            $status = Listing::STATUS_ACTIVE;
        }

        $counts = collect(self::TABS)
            ->mapWithKeys(fn (string $_, string $key): array => [
                $key => $company->listings()->where('status', $key)->count(),
            ])
            ->all();

        $listings = $company->listings()
            ->with(['category.translations', 'activePromotions.type'])
            ->where('status', $status)
            ->latest('updated_at')
            ->get()
            ->map(fn (Listing $l): array => $this->present($l));

        return Inertia::render('cabinet/listings/Index', [
            'listings' => $listings,
            'counts' => $counts,
            'tabs' => self::TABS,
            'status' => $status,
            'limit' => [
                'used' => $counts[Listing::STATUS_ACTIVE],
                'total' => $company->plan()->listings_limit,
            ],
        ]);
    }

    /** @return array<string, mixed> */
    private function present(Listing $listing): array
    {
        return [
            'id' => $listing->id,
            'title' => $listing->title,
            'type' => $listing->type,
            'category' => $listing->category?->name(),
            'price' => $listing->price !== null ? (float) $listing->price : null,
            'currency' => $listing->currency,
            'unit' => $listing->unit,
            'negotiable' => $listing->price_negotiable,
            'status' => $listing->status,
            'moderation_note' => $listing->moderation_note,
            'impressions' => $listing->impressions_count,
            'views' => $listing->views_count,
            'unlocks' => $listing->unlocks_count,
            'expires_at' => $listing->expires_at?->translatedFormat('d.m.Y'),
            'expiring_soon' => $listing->isExpiringSoon(),
            'badges' => $listing->activePromotions
                ->map(fn ($p): ?string => $p->type?->badge)
                ->filter()
                ->values(),
        ];
    }

    /**
     * Продление публикации.
     *
     * Лимит тарифа проверяется здесь так же, как при публикации.
     * Без этого он обходился за минуту: опубликовать до лимита,
     * заархивировать, опубликовать ещё — а потом одним массовым
     * действием продлить всё разом. Проверка только в мастере
     * закрывала лишь один из трёх путей в статус «активно».
     */
    public function renew(Request $request, int $id): RedirectResponse
    {
        $listing = $this->ownedListing($request, $id);
        $company = $listing->company;

        if (! $this->hasFreeSlot($company, [$listing->id])) {
            return back()->with('error', $this->limitMessage($company));
        }

        $this->activate($listing, $company);

        return back()->with('success', 'Объявление продлено до '.$listing->expires_at->translatedFormat('d.m.Y'));
    }

    /**
     * Перевод объявления в «активно».
     *
     * Срок отсчитывается от текущего момента, а не от даты истечения:
     * иначе объявление, пролежавшее месяц просроченным, продлевается
     * «назад» и снова оказывается истёкшим.
     *
     * Длительность берётся из тарифа: на Free объявление живёт месяц,
     * на Premium — полгода, и это часть того, за что платят.
     *
     * Компания передаётся аргументом, а не читается из связи: при
     * массовом продлении это дало бы запрос на каждое объявление,
     * а с отключённой ленивой загрузкой — исключение.
     */
    private function activate(Listing $listing, Company $company): void
    {
        $listing->forceFill([
            'status' => Listing::STATUS_ACTIVE,
            'expires_at' => now()->addDays($company->plan()->listing_days ?? Listing::LIFETIME_DAYS),
            'published_at' => $listing->published_at ?? now(),
        ])->save();
    }

    /**
     * Есть ли свободный слот под ещё одно активное объявление.
     *
     * @param  list<int>  $excludeIds  объявления, которые сами становятся активными
     */
    private function hasFreeSlot(Company $company, array $excludeIds = []): bool
    {
        $limit = $company->plan()->listings_limit;

        if ($limit === null) {
            return true;
        }

        $active = $company->activeListings()->whereNotIn('id', $excludeIds)->count();

        return $active < $limit;
    }

    private function limitMessage(Company $company): string
    {
        $plan = $company->plan();

        return "Достигнут лимит тарифа {$plan->name}: {$plan->listings_limit} активных объявлений."
            .' Снимите ненужное с публикации или смените тариф.';
    }

    public function archive(Request $request, int $id): RedirectResponse
    {
        $listing = $this->ownedListing($request, $id);

        $listing->forceFill(['status' => Listing::STATUS_ARCHIVED])->save();

        return back()->with('success', 'Объявление снято с публикации');
    }

    public function destroy(Request $request, int $id): RedirectResponse
    {
        $this->ownedListing($request, $id)->delete();

        return back()->with('success', 'Объявление удалено');
    }

    /**
     * Массовое действие над выбранными объявлениями.
     *
     * Выбор фильтруется по владельцу одним запросом: проверять каждый id
     * отдельно значит открыть возможность подмешать чужой.
     */
    public function bulk(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'action' => ['required', 'in:renew,archive,delete'],
            'ids' => ['required', 'array', 'min:1'],
            'ids.*' => ['integer'],
        ]);

        $company = $request->user()->company;

        if ($company === null) {
            return back();
        }

        $listings = $company->listings()->whereIn('id', $data['ids'])->get();

        if ($listings->isEmpty()) {
            return back()->with('error', 'Ничего не выбрано');
        }

        /*
         * Продление считает лимит на всю пачку сразу, а не по одному:
         * иначе десять объявлений при свободном одном слоте прошли бы
         * по очереди, каждое видя актуальный на свой момент остаток.
         */
        if ($data['action'] === 'renew') {
            $limit = $company->plan()->listings_limit;

            if ($limit !== null) {
                $ids = $listings->pluck('id')->all();
                $othersActive = $company->activeListings()->whereNotIn('id', $ids)->count();

                if ($othersActive + $listings->count() > $limit) {
                    $free = max(0, $limit - $othersActive);

                    return back()->with('error', $this->limitMessage($company)
                        ." Свободных слотов: {$free}, выбрано: {$listings->count()}.");
                }
            }
        }

        foreach ($listings as $listing) {
            match ($data['action']) {
                'renew' => $this->activate($listing, $company),
                'archive' => $listing->forceFill(['status' => Listing::STATUS_ARCHIVED])->save(),
                'delete' => $listing->delete(),
            };
        }

        $word = trans_choice('{1}объявление|[2,4]объявления|[5,*]объявлений', $listings->count());

        return back()->with('success', match ($data['action']) {
            'renew' => "Продлено: {$listings->count()} {$word}",
            'archive' => "Снято с публикации: {$listings->count()} {$word}",
            'delete' => "Удалено: {$listings->count()} {$word}",
        });
    }

    /** Отправить отклонённое объявление на повторную проверку. */
    public function resubmit(Request $request, int $id): RedirectResponse
    {
        $listing = $this->ownedListing($request, $id);

        $listing->forceFill([
            'status' => Listing::STATUS_MODERATION,
            'moderation_note' => null,
        ])->save();

        app(Notifier::class)->company(
            $listing->company,
            'moderation',
            "Объявление «{$listing->title}» отправлено на повторную проверку",
            ['url' => route('cabinet.listings', ['status' => Listing::STATUS_MODERATION])],
        );

        return back()->with('success', 'Отправлено на проверку');
    }

    /**
     * Объявление текущей компании либо 404.
     *
     * Именно 404, а не 403: сообщать «такое объявление есть, но не ваше»
     * значит подтверждать существование чужой записи по её номеру.
     */
    private function ownedListing(Request $request, int $id): Listing
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $listing = $company->listings()->find($id);

        abort_if($listing === null, 404);

        return $listing;
    }
}
