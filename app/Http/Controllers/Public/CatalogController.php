<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Category;
use App\Models\City;
use App\Models\CompanyContact;
use App\Models\Listing;
use App\Support\ListingCard;
use App\Support\ListingTags;
use App\Support\SeoBuilders;
use App\Support\StatsRecorder;
use Illuminate\Contracts\Database\Eloquent\Builder;
use Illuminate\Http\Request;
use Illuminate\Support\Collection;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Каталог объявлений — витрина площадки.
 *
 * Ранжирование учитывает купленное продвижение, но не подменяет им
 * органическую выдачу: продвинутые объявления помечаются словом
 * «Продвигается» (§3.4 ТЗ). Выдавать рекламу за обычную выдачу
 * площадка не будет — это заявлено на витрине.
 */
class CatalogController extends Controller
{
    private const PER_PAGE = 20;

    private const SORT_KEYS = ['relevant', 'fresh', 'cheap', 'expensive'];

    /**
     * Подписи сортировок — из словаря: селект в каталоге должен
     * говорить на языке страницы, как и весь остальной интерфейс.
     *
     * @return array<string, string>
     */
    private function sorts(): array
    {
        return array_combine(
            self::SORT_KEYS,
            array_map(fn (string $key): string => __("ui.catalog.sort_{$key}"), self::SORT_KEYS),
        );
    }

    public function __construct(
        private readonly StatsRecorder $stats,
        private readonly SeoBuilders $seo,
    ) {}

    public function index(Request $request): Response
    {
        $query = $request->string('q')->toString();
        $sort = $request->string('sort')->toString();

        if (! in_array($sort, self::SORT_KEYS, true)) {
            $sort = 'relevant';
        }

        $listings = Listing::query()
            ->with(ListingCard::relations())
            ->where('status', Listing::STATUS_ACTIVE)
            // Объявление заблокированной компании не должно висеть в выдаче
            ->whereHas('company', fn (Builder $q) => $q->where('status', 'active'))
            ->when($query !== '', fn (Builder $q) => $q->search($query))
            ->when($request->string('type')->toString(), fn (Builder $q, string $type) => $q->where('type', $type))
            ->when($request->integer('category'), fn (Builder $q, int $id) => $this->applyCategory($q, $id))
            ->when($request->integer('city'), fn (Builder $q, int $id) => $q->where('city_id', $id))
            ->when($request->boolean('verified'), fn (Builder $q) => $q->whereHas(
                'company',
                fn (Builder $c) => $c->where('verification_level', '>=', 2),
            ))
            ->when($request->boolean('with_price'), fn (Builder $q) => $q
                ->whereNotNull('price')
                ->where('price_negotiable', false))
            ->tap(fn (Builder $q) => $this->applySort($q, $sort))
            ->paginate(self::PER_PAGE)
            ->withQueryString();

        // Показы засчитываются тому, что реально попало в выдачу
        $this->recordImpressions($listings->getCollection(), $query);

        /*
         * Заголовок собирается из выбранных фильтров: «Цемент оптом
         * в Ташкенте» — то, что набирают в поиске, «Каталог объявлений» —
         * то, что не набирают никогда.
         */
        $this->seo->catalog(
            [
                'query' => $query !== '' ? $query : null,
                'category' => $request->integer('category') !== 0
                    ? Category::find($request->integer('category'))?->name()
                    : null,
                'city' => $request->integer('city') !== 0
                    ? City::find($request->integer('city'))?->name()
                    : null,
            ],
            $listings->total(),
            // Любой фильтр или страница со второй — уже не главная
            // версия каталога, и в индексе ей делать нечего
            filtered: $request->hasAny(['q', 'type', 'category', 'city', 'verified', 'with_price', 'sort'])
                || $listings->currentPage() > 1,
        );

        return Inertia::render('catalog/Index', [
            'listings' => $listings->through(fn (Listing $l): array => $this->present($l)),
            'filters' => [
                'q' => $query,
                'type' => $request->string('type')->toString(),
                'category' => $request->integer('category') ?: null,
                'city' => $request->integer('city') ?: null,
                'verified' => $request->boolean('verified'),
                'with_price' => $request->boolean('with_price'),
                'sort' => $sort,
            ],
            'sorts' => $this->sorts(),
            'categories' => $this->categories(),
            'cities' => $this->cities(),
            'total' => $listings->total(),
        ]);
    }

    /** Категория раздела включает все подкатегории — иначе фильтр пуст. */
    private function applyCategory(Builder $query, int $categoryId): void
    {
        $ids = Category::query()
            ->where('id', $categoryId)
            ->orWhere('parent_id', $categoryId)
            ->pluck('id');

        $query->whereIn('category_id', $ids);
    }

    /**
     * Порядок выдачи.
     *
     * «Подходящие» — продвинутые выше, затем свежие. Продвижение даёт
     * приоритет внутри выдачи, но не выбрасывает органику: объявление
     * без продвижения всё равно попадает на первую страницу, если оно
     * свежее.
     */
    private function applySort(Builder $query, string $sort): void
    {
        match ($sort) {
            'fresh' => $query->latest('published_at'),
            'cheap' => $query->orderByRaw('price is null, price asc'),
            'expensive' => $query->orderByRaw('price is null, price desc'),
            default => $query
                ->withCount(['activePromotions as promoted' => fn (Builder $q) => $q->whereHas(
                    'type',
                    fn (Builder $t) => $t->whereIn('code', ['category_top', 'home_top', 'bump', 'urgent']),
                )])
                ->orderByDesc('promoted')
                ->latest('published_at'),
        };
    }

    /** @param Collection<int, Listing> $listings */
    private function recordImpressions($listings, string $query): void
    {
        if ($listings->isEmpty()) {
            return;
        }

        $this->stats->impressions($listings->pluck('id')->all());

        // Поисковый запрос засчитывается каждой показанной компании:
        // раздел «по каким запросам вас находили» строится именно так.
        // Одним вызовом на весь список: цикл давал по паре запросов
        // на компанию при каждом заходе на страницу поиска
        if ($query !== '') {
            $this->stats->search(
                $listings->pluck('company_id')->unique()->map(fn ($id): int => (int) $id)->values()->all(),
                $query,
            );
        }
    }

    /**
     * Карточка объявления. Форма данных общая для всех списков —
     * см. ListingCard: главная, каталог и избранное рисуют одно и то же.
     *
     * @return array<string, mixed>
     */
    private function present(Listing $listing): array
    {
        return ListingCard::present($listing);
    }

    /** @return list<array<string, mixed>> */
    private function categories(): array
    {
        return Category::query()
            ->whereNull('parent_id')
            ->where('is_active', true)
            ->with(['translations', 'children.translations'])
            ->withCount(['listings as active_count' => fn (Builder $q) => $q->where('status', Listing::STATUS_ACTIVE)])
            ->orderBy('sort')
            ->get()
            ->map(fn (Category $c): array => [
                'id' => $c->id,
                'name' => $c->name(),
                'children' => $c->children->map(fn (Category $child): array => [
                    'id' => $child->id,
                    'name' => $child->name(),
                ]),
            ])
            ->all();
    }

    /** @return list<array<string, mixed>> */
    private function cities(): array
    {
        return City::query()
            ->where('is_active', true)
            ->with('translations')
            ->whereHas('listings', fn (Builder $q) => $q->where('status', Listing::STATUS_ACTIVE))
            ->get()
            ->map(fn (City $c): array => ['id' => $c->id, 'name' => $c->name()])
            ->sortBy('name')
            ->values()
            ->all();
    }

    /** Карточка объявления. */
    public function show(Request $request, string $slug): Response
    {
        $listing = Listing::query()
            ->with([
                'company.city.translations',
                'company.country.translations',
                'company.publicContacts',
                'category.translations',
                'category.parent.translations',
                'category.fields',
                'attributes',
                'activePromotions.type',
                'images',
            ])
            ->where('slug', $slug)
            ->firstOrFail();

        /*
         * Предпросмотр: владелец открывает своё объявление в любом
         * статусе и видит его в точности так, как увидят покупатели.
         * Для остальных неопубликованное объявление не существует —
         * 404, а не 403: черновик не должен подтверждать, что он есть.
         */
        $isOwner = $request->user()?->company_id === $listing->company_id;
        $preview = $listing->status !== Listing::STATUS_ACTIVE;

        abort_if($preview && ! $isOwner, 404);

        // Просмотры предпросмотра не считаются: это взгляд владельца
        // в зеркало, а не интерес покупателя
        if (! $preview) {
            $this->stats->view($listing);
        }

        $this->seo->listing($listing);

        $company = $listing->company;
        $viewerCompanyId = $request->user()?->company_id;

        $unlocked = $viewerCompanyId !== null && (
            $viewerCompanyId === $company->id
            || $company->unlockedBy()->where('company_id', $viewerCompanyId)->exists()
        );

        return Inertia::render('catalog/Show', [
            'listing' => [
                'id' => $listing->id,
                'title' => $listing->title,
                'description' => $listing->description,
                'type' => $listing->type,
                'category' => $listing->category?->name(),
                'price' => $listing->price !== null ? (float) $listing->price : null,
                'bundle_price' => $listing->bundle_price !== null ? (float) $listing->bundle_price : null,
                'currency' => $listing->currency,
                'unit' => $listing->unit,
                'negotiable' => $listing->price_negotiable,
                'min_order' => $listing->min_order,
                'delivery_terms' => $listing->delivery_terms,
                'payment_terms' => $listing->payment_terms,
                'city' => $company?->city?->name(),
                'published' => $listing->published_at?->translatedFormat('d.m.Y'),
                'expires' => $listing->expires_at?->translatedFormat('d.m.Y'),
                'views' => $listing->views_count,
                /*
                 * Подписи характеристик — из полей категории, а не ключи
                 * как есть: покупатель должен видеть «Марка», а не mark.
                 * Ключ без описания в справочнике остаётся как записан.
                 */
                'attributes' => $listing->attributes->map(fn ($a): array => [
                    'key' => $listing->category?->fields
                        ->firstWhere('key', $a->key)?->label ?? $a->key,
                    'value' => $a->value,
                ]),
                'badges' => $listing->activePromotions->map(fn ($p): ?string => $p->type?->badge)->filter()->values(),
                'promoted' => $listing->activePromotions->isNotEmpty(),

                // Теги — автоматически из заголовка, категории
                // и характеристик; клик по тегу ведёт в поиск каталога
                'tags' => ListingTags::for($listing),
                'images' => $listing->images->map(fn ($i): array => [
                    'id' => $i->id,
                    'url' => $i->url(),
                    'thumb' => $i->thumbUrl(),
                ])->values(),
            ],

            'company' => [
                'name' => $company?->name,
                'slug' => $company?->slug,
                'initials' => $company?->initials(),
                'verification_level' => (int) ($company?->verification_level ?? 0),
                'rating' => (float) ($company?->rating ?? 0),
                'reviews_count' => (int) ($company?->reviews_count ?? 0),
                'city' => $company?->city?->name(),
                'country' => $company?->country?->name(),
            ],

            // Контакты маскируются на сервере — как и на визитке
            'contacts' => $company?->publicContacts->map(fn ($c): array => [
                'type' => $c->type,
                'value' => $unlocked || in_array($c->type, CompanyContact::PUBLIC_TYPES, true)
                    ? $c->value
                    : $c->masked(),
                'href' => $unlocked || in_array($c->type, CompanyContact::PUBLIC_TYPES, true)
                    ? $c->href()
                    : null,
                'locked' => ! $unlocked && ! in_array($c->type, CompanyContact::PUBLIC_TYPES, true),
            ]) ?? [],

            'unlocked' => $unlocked,

            // Плашка «это предпросмотр» — только владельцу
            // неопубликованного объявления; остальные сюда не доходят
            'preview' => $preview,

            /*
             * Можно ли откликнуться. Гостю кнопка ведёт на вход,
             * владельцу не показывается вовсе: отклик на собственное
             * объявление сервер всё равно отклонит.
             */
            'respond' => [
                'guest' => $request->user() === null,
                'owner' => $viewerCompanyId !== null && $viewerCompanyId === $company?->id,
            ],

            'similar' => $this->similar($listing),
        ]);
    }

    /** @return list<array<string, mixed>> */
    private function similar(Listing $listing): array
    {
        return Listing::query()
            ->with(ListingCard::relations())
            ->where('status', Listing::STATUS_ACTIVE)
            // Как и в выдаче: объявление заблокированной компании
            // не должно висеть в блоке похожих
            ->whereHas('company', fn (Builder $q) => $q->where('status', 'active'))
            ->where('id', '!=', $listing->id)
            ->when($listing->category_id !== null, fn (Builder $q) => $q->where('category_id', $listing->category_id))
            ->latest('published_at')
            ->limit(4)
            ->get()
            ->map(fn (Listing $l): array => $this->present($l))
            ->all();
    }
}
