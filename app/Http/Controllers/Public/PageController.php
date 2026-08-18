<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Category;
use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Models\Listing;
use App\Models\Plan;
use App\Models\Review;
use App\Models\Setting;
use App\Support\CurrencyRate;
use App\Support\ListingCard;
use App\Support\NewsRepository;
use App\Support\OfficeLocation;
use App\Support\Seo;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Публичные страницы: главная, о компании, тарифы, страны, контакты.
 *
 * Содержимое пока задано в коде. По §6.5–6.6 ТЗ оно переедет
 * в page_blocks и будет редактироваться из админки (спринт 13).
 */
class PageController extends Controller
{
    public function home(NewsRepository $news): Response
    {
        $stats = $this->stats();

        app(Seo::class)
            ->title(__('ui.seo.home_title'))
            ->description(__('ui.seo.home_description', [
                'listings' => $stats['listings'],
                'companies' => $stats['companies'],
            ]))
            ->canonical(url('/'))
            /*
             * Строка поиска в выдаче Google: по запросу «savdex» под
             * ссылкой появляется поле, которое ведёт прямо в каталог.
             */
            ->schema([
                '@type' => 'WebSite',
                'name' => 'SAVDEX',
                'url' => url('/'),
                'potentialAction' => [
                    '@type' => 'SearchAction',
                    'target' => ['@type' => 'EntryPoint', 'urlTemplate' => url('/catalog?q={search_term_string}')],
                    'query-input' => 'required name=search_term_string',
                ],
            ]);

        /*
         * FAQ размечается и для поисковика: по вопросам из него Google
         * показывает раскрывающиеся ответы прямо в выдаче. Источник
         * один — словарь: расхождение текста на странице и в разметке
         * поисковики наказывают.
         */
        app(Seo::class)->schema([
            '@type' => 'FAQPage',
            'mainEntity' => array_map(fn (int $i): array => [
                '@type' => 'Question',
                'name' => __("ui.home.faq_q{$i}"),
                'acceptedAnswer' => ['@type' => 'Answer', 'text' => __("ui.home.faq_a{$i}")],
            ], range(1, 6)),
        ]);

        return Inertia::render('Home', [
            'stats' => $stats,
            'categories' => $this->popularCategories(),
            // Лента товаров первого экрана: только предложения —
            // запросы идут отдельной лентой ниже
            'latest' => $this->latestListings(),
            // Лента запросов на закупку (RFQ): другая сторона площадки
            'requests' => $this->latestRequests(),
            // Витрина поставщиков: покупатель фильтруется по блокам —
            // кто ищет товар, уходит в ленту выше, кто ищет партнёра — сюда
            'suppliers' => $this->topSuppliers(),
            'countries' => $this->countryOptions(),
            // Города для выбора локации в поиске первого экрана
            'cities' => $this->cityOptions(),
            // Свежие новости прямо на главной: раздел, до которого
            // нужно ещё дойти по меню, читают в разы меньше
            'news' => $news->latest(4),
            // Отзывы пользователей: живое социальное доказательство
            // вместо обещаний площадки о самой себе
            'reviews' => $this->latestReviews(),
        ]);
    }

    public function about(): Response
    {
        app(Seo::class)
            ->title(__('ui.seo.about_title'))
            ->description(__('ui.seo.about_description'))
            ->canonical(url('/about'));

        $office = OfficeLocation::current();

        /*
         * Адрес офиса размечается для поисковика: по нему организация
         * попадает в карточку компании в выдаче и на карты. Разметка
         * появляется только вместе с заполненной настройкой — пустой
         * PostalAddress поисковики считают ошибкой разметки.
         */
        if ($office !== null) {
            app(Seo::class)->organizationDetails([
                'legalName' => (string) Setting::get('legal_name', ''),
                'email' => (string) Setting::get('support_email', ''),
                'telephone' => (string) Setting::get('support_phone', ''),
                'address' => $office['address'] !== '' ? [
                    '@type' => 'PostalAddress',
                    'streetAddress' => $office['address'],
                    'addressCountry' => 'UZ',
                ] : null,
                'geo' => $office['lat'] !== null ? [
                    '@type' => 'GeoCoordinates',
                    'latitude' => $office['lat'],
                    'longitude' => $office['lng'],
                ] : null,
            ]);
        }

        return Inertia::render('About', [
            'stats' => $this->stats(),
            // Офис приходит с сервера, а не жёстко лежит в вёрстке:
            // адрес и точку на карте меняет администратор в настройках
            'office' => $office,
        ]);
    }

    public function pricing(): Response
    {
        app(Seo::class)
            ->title(__('ui.seo.pricing_title'))
            ->description(__('ui.seo.pricing_description'))
            ->canonical(url('/pricing'));

        /*
         * Тарифы и цены — из базы, как в кабинете (BillingController).
         * Один источник: цену меняют в админке или сидере, и витрина
         * с кассой не могут разойтись.
         */
        $rate = app(CurrencyRate::class)->usd();

        return Inertia::render('Pricing', [
            'plans' => Plan::query()->where('is_active', true)->orderBy('sort')->get()
                ->map(fn (Plan $p): array => [
                    'code' => $p->code,
                    'name' => $p->name,
                    'price_uzs' => $p->priceUzs($rate),
                    'listings_limit' => $p->listings_limit,
                    'contacts_limit' => $p->contacts_limit,
                    'promo_units' => $p->promo_units,
                    'listing_days' => $p->listing_days,
                    'has_microsite' => $p->has_microsite,
                    'advanced_analytics' => $p->advanced_analytics,
                ]),
        ]);
    }

    /**
     * Страны-участники: каждая карточка ведёт в каталог компаний
     * с фильтром по стране. Список живой — из справочника, а не из
     * вёрстки: страна появляется здесь вместе с первой компанией.
     */
    public function countries(): Response
    {
        app(Seo::class)
            ->title(__('ui.seo.countries_title'))
            ->description(__('ui.seo.countries_description'))
            ->canonical(url('/countries'));

        $companyCounts = Company::query()
            ->where('status', Company::STATUS_ACTIVE)
            ->whereNotNull('country_id')
            ->selectRaw('country_id, count(*) as total')
            ->groupBy('country_id')
            ->pluck('total', 'country_id');

        $countries = Country::query()
            ->where('is_active', true)
            ->with('translations')
            ->orderBy('sort')
            ->get()
            ->map(fn (Country $c): array => [
                'code' => $c->code,
                'name' => $c->name(),
                'companies' => (int) ($companyCounts[$c->id] ?? 0),
            ])
            // Страны с компаниями — вперёд: пустая карточка в начале
            // списка продаёт площадку хуже, чем есть
            ->sortByDesc('companies')
            ->values()
            ->all();

        return Inertia::render('Countries', ['countries' => $countries]);
    }

    /**
     * Партнёры площадки — витрина проверенных компаний.
     *
     * Показываем верхушку по проверке и рейтингу: страница продаёт
     * доверие, а не полный справочник, поэтому здесь только компании
     * с подтверждёнными документами. Полный каталог — по ссылке ниже.
     * Порядок тот же, что в каталоге компаний, чтобы витрина сходилась
     * с тем, что человек увидит, нажав «Все компании».
     */
    public function partners(): Response
    {
        app(Seo::class)
            ->title(__('ui.seo.partners_title'))
            ->description(__('ui.seo.partners_description'))
            ->canonical(url('/partners'));

        $partners = Company::query()
            ->with(['city.translations', 'country.translations'])
            ->where('status', Company::STATUS_ACTIVE)
            ->where('verification_level', '>=', Company::VERIFICATION_COMPANY)
            ->orderByDesc('verification_level')
            ->orderByDesc('rating')
            ->orderByDesc('completed_deals_count')
            ->limit(24)
            ->get()
            ->map(fn (Company $c): array => [
                'slug' => $c->slug,
                'name' => $c->name,
                'type_label' => $c->typeLabel(),
                'city' => $c->city?->name(),
                'country' => $c->country?->name(),
                'verification_level' => $c->verification_level,
                'rating' => (float) $c->rating,
                'reviews_count' => $c->reviews_count,
                'completed_deals_count' => $c->completed_deals_count,
                'initials' => $c->initials(),
                'logo' => $c->logoUrl(),
            ])
            ->all();

        return Inertia::render('Partners', [
            'partners' => $partners,
            'stats' => [
                'total' => Company::where('status', Company::STATUS_ACTIVE)->count(),
                'verified' => Company::where('status', Company::STATUS_ACTIVE)
                    ->where('verification_level', '>=', Company::VERIFICATION_COMPANY)
                    ->count(),
                'deals' => (int) Company::where('status', Company::STATUS_ACTIVE)->sum('completed_deals_count'),
            ],
        ]);
    }

    /** Контакты площадки. Реквизиты — из словаря, как и весь текст. */
    public function contacts(): Response
    {
        // Маршрут — /contact без «s»: canonical обязан совпадать
        // с живым адресом, иначе он ведёт на 404 и игнорируется
        app(Seo::class)
            ->title(__('ui.seo.contacts_title'))
            ->description(__('ui.seo.contacts_description'))
            ->canonical(url('/contact'));

        return Inertia::render('Contacts');
    }

    /**
     * Счётчики витрины — все из базы.
     *
     * Без кэша намеренно. Площадка растёт по одной компании, и человек,
     * зарегистрировавшийся минуту назад, должен увидеть себя в счётчике,
     * а не прежнюю цифру. COUNT по индексированным колонкам этого
     * стоят; появится нагрузка — вернём кэш вместе со сбросом при записи.
     *
     * «Сделки» — сумма завершённых сделок по активным компаниям:
     * поле ведётся по каждой компании и показывается на её карточке,
     * значит и общий счётчик обязан сходиться с суммой карточек.
     *
     * @return array{companies: int, listings: int, categories: int, countries: int, deals: int}
     */
    private function stats(): array
    {
        return [
            'companies' => Company::where('status', Company::STATUS_ACTIVE)->count(),
            'listings' => Listing::where('status', Listing::STATUS_ACTIVE)->count(),
            // Считаем подкатегории: разделов верхнего уровня шесть,
            // и «6 категорий товаров» продаёт площадку хуже, чем есть
            'categories' => Category::where('is_active', true)->whereNotNull('parent_id')->count(),
            'countries' => Country::where('is_active', true)->count(),
            'deals' => (int) Company::where('status', Company::STATUS_ACTIVE)->sum('completed_deals_count'),
        ];
    }

    /**
     * Разделы каталога для плитки «Популярные категории».
     *
     * Счётчик объявлений включает подкатегории: объявления привязаны
     * к ним, и раздел с нулём при живых подразделах выглядел бы пустым.
     *
     * @return list<array{id: int, name: string, icon: string|null, listings: int}>
     */
    private function popularCategories(): array
    {
        $counts = Listing::query()
            ->where('status', Listing::STATUS_ACTIVE)
            ->whereNotNull('category_id')
            ->selectRaw('category_id, count(*) as total')
            ->groupBy('category_id')
            ->pluck('total', 'category_id');

        return Category::query()
            ->whereNull('parent_id')
            ->where('is_active', true)
            ->with(['translations', 'children:id,parent_id'])
            ->orderBy('sort')
            ->get()
            ->map(fn (Category $c): array => [
                'id' => $c->id,
                'name' => $c->name(),
                'icon' => $c->icon,
                'listings' => (int) ($counts[$c->id] ?? 0)
                    + $c->children->sum(fn (Category $child): int => (int) ($counts[$child->id] ?? 0)),
            ])
            // Разделы без единого объявления не показываются: плитка
            // с нулём зовёт в пустоту и продаёт площадку хуже, чем есть
            ->filter(fn (array $c): bool => $c['listings'] > 0)
            ->values()
            ->all();
    }

    /** @return list<array<string, mixed>> */
    private function latestListings(): array
    {
        return Listing::query()
            ->with(ListingCard::relations())
            // Продвинутые (ТОП/Срочно) — всегда первыми: это оплаченное
            // место в ленте, покупатель платит именно за него
            ->withCount(['promotions as boosted' => fn ($q) => $q->where('status', 'active')])
            ->where('status', Listing::STATUS_ACTIVE)
            ->where('type', Listing::TYPE_SUPPLY)
            ->whereHas('company', fn ($q) => $q->where('status', Company::STATUS_ACTIVE))
            ->orderByDesc('boosted')
            ->latest('published_at')
            ->limit(12)
            ->get()
            ->map(fn (Listing $l): array => ListingCard::present($l))
            ->all();
    }

    /**
     * Свежие запросы на закупку (RFQ) для отдельной ленты главной.
     *
     * Зеркало latestListings, но по типу «спрос»: это другая сторона
     * площадки — не «продаю», а «куплю». Своя лента, а не вперемешку
     * с товарами: покупатель и поставщик ищут в ней разное.
     *
     * @return list<array<string, mixed>>
     */
    private function latestRequests(): array
    {
        return Listing::query()
            ->with(ListingCard::relations())
            ->where('status', Listing::STATUS_ACTIVE)
            ->where('type', Listing::TYPE_DEMAND)
            ->whereHas('company', fn ($q) => $q->where('status', Company::STATUS_ACTIVE))
            ->latest('published_at')
            ->limit(8)
            ->get()
            ->map(fn (Listing $l): array => ListingCard::present($l))
            ->all();
    }

    /**
     * Витрина поставщиков для главной: лучшие по проверке и рейтингу.
     *
     * Порядок тот же, что в каталоге компаний, — витрина обязана
     * сходиться с тем, что человек увидит, нажав «Все компании».
     *
     * @return list<array<string, mixed>>
     */
    private function topSuppliers(): array
    {
        return Company::query()
            ->with(['city.translations'])
            ->where('status', Company::STATUS_ACTIVE)
            ->orderByDesc('verification_level')
            ->orderByDesc('rating')
            ->limit(4)
            ->get()
            ->map(fn (Company $c): array => [
                'slug' => $c->slug,
                'name' => $c->name,
                'type_label' => $c->typeLabel(),
                'city' => $c->city?->name(),
                'verification_level' => $c->verification_level,
                'rating' => (float) $c->rating,
                'reviews_count' => $c->reviews_count,
                'completed_deals_count' => $c->completed_deals_count,
                'initials' => $c->initials(),
                'logo' => $c->logoUrl(),
            ])
            ->all();
    }

    /**
     * Свежие отзывы для витрины главной.
     *
     * Только опубликованные и только между живыми компаниями: отзыв
     * без автора или об исчезнувшей компании на витрине выглядел бы
     * выдуманным. Тексты — из базы, как и счётчики: сочинённые
     * цитаты на витрине недопустимы.
     *
     * @return list<array<string, mixed>>
     */
    private function latestReviews(): array
    {
        return Review::query()
            ->with(['company:id,slug,name', 'authorCompany:id,name'])
            ->where('status', Review::STATUS_PUBLISHED)
            ->whereHas('company', fn ($q) => $q->where('status', Company::STATUS_ACTIVE))
            ->whereHas('authorCompany')
            ->latest()
            ->limit(3)
            ->get()
            ->map(fn (Review $r): array => [
                'id' => $r->id,
                'author' => $r->authorCompany->name,
                'initials' => $r->authorCompany->initials(),
                'rating' => (int) $r->rating,
                'body' => $r->body,
                'when' => $r->created_at->translatedFormat('d.m.Y'),
                'company_name' => $r->company->name,
                'company_slug' => $r->company->slug,
            ])
            ->all();
    }

    /**
     * Страны для выпадающего списка поиска на первом экране.
     *
     * @return list<array{code: string, name: string}>
     */
    private function countryOptions(): array
    {
        return Country::query()
            ->where('is_active', true)
            ->with('translations')
            ->orderBy('sort')
            ->get()
            ->map(fn (Country $c): array => ['code' => $c->code, 'name' => $c->name()])
            ->all();
    }

    /**
     * Города для выбора локации в поиске первого экрана.
     *
     * Только те, где есть живые объявления: локация без единого
     * объявления в фильтре зовёт в пустую выдачу.
     *
     * @return list<array{id: int, name: string}>
     */
    private function cityOptions(): array
    {
        return City::query()
            ->where('is_active', true)
            ->with('translations')
            ->whereHas('listings', fn ($q) => $q->where('status', Listing::STATUS_ACTIVE))
            ->get()
            ->map(fn (City $c): array => ['id' => $c->id, 'name' => $c->name()])
            ->sortBy('name')
            ->values()
            ->all();
    }
}
