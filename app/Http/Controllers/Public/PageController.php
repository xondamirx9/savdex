<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Exceptions\PromoCodeRejected;
use App\Http\Controllers\Controller;
use App\Models\Banner;
use App\Models\Category;
use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Models\ItTask;
use App\Models\Listing;
use App\Models\Plan;
use App\Models\Review;
use App\Models\Setting;
use App\Services\OrderService;
use App\Services\PromoCodeService;
use App\Support\Appearance;
use App\Support\BannerCard;
use App\Support\ContentTranslation;
use App\Support\CurrencyRate;
use App\Support\ListingCard;
use App\Support\NewsRepository;
use App\Support\OfficeLocation;
use App\Support\Seo;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\RateLimiter;
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
            // Без живых счётчиков: «9 объявлений» в сниппете Google
            // и в превью мессенджеров продаёт площадку хуже, чем есть
            ->description(__('ui.seo.home_description'))
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
            // Баннер акции — сразу под первым экраном. Пусто, если
            // сейчас ничего не идёт: место не резервируется
            'banner' => BannerCard::forPlacement(Banner::PLACEMENT_HOME),
            // Фон первого экрана: меняется в админке, в разделе
            // «Оформление». Пустая настройка даёт картинку из коробки
            'heroImage' => Appearance::heroImage(),
            // Пропорции кадра: первый экран повторяет их, чтобы фото
            // было видно целиком — без обрезки и без поля под кадром
            'heroRatio' => Appearance::heroImageRatio(),
            'categories' => $this->popularCategories(),
            // Две плитки «Доп. услуг» рядом с категориями товаров
            'services' => $this->popularServices(),
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

    public function pricing(Request $request): Response
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
        [$promo, $promoError] = $this->pricingPromo($request);

        return Inertia::render('Pricing', [
            'promo' => $promo !== null ? [
                'code' => $promo['code'],
                'plan_code' => $promo['plan_code'],
                'discount_percent' => $promo['discount_percent'],
                'days' => $promo['days'],
            ] : null,
            'promoError' => $promoError,
            'plans' => Plan::query()->where('is_active', true)->orderBy('sort')->get()
                ->map(fn (Plan $p): array => [
                    'code' => $p->code,
                    'name' => $p->name,
                    'price_uzs' => $p->priceUzs($rate),
                    // Долларовая цена — из тарифа как задана (подход
                    // InvestIn): сумовая выводится из неё по курсу,
                    // и витрина показывает обе
                    'price_usd' => (float) $p->price_usd,
                    'listings_limit' => $p->listings_limit,
                    'contacts_limit' => $p->contacts_limit,
                    'responses_limit' => $p->responses_limit,
                    'promo_units' => $p->promo_units,
                    'listing_days' => $p->listing_days,
                    'verification_days' => $p->verification_days,
                    'sees_interested_names' => $p->sees_interested_names,
                    'has_microsite' => $p->has_microsite,
                    'advanced_analytics' => $p->advanced_analytics,
                    'promo_price' => $promo !== null && $promo['plan_id'] === $p->id
                        ? self::promoPrice($p, $promo, $rate)
                        : null,
                ]),
        ]);
    }

    /**
     * Промокод, введённый на странице тарифов (?promo=КОД).
     *
     * Код здесь только проверяется, а не гасится: гасит его активация
     * в кабинете. Адрес с кодом можно давать ссылкой — с листовки или
     * из рассылки человек сразу видит свою цену.
     *
     * Попыток — десять в час с адреса, как у активации: проверка
     * отвечает «такого кода нет», и без предела по ней перебирали бы коды.
     *
     * @return array{0: array<string, mixed>|null, 1: string|null}
     */
    private function pricingPromo(Request $request): array
    {
        $input = trim((string) $request->query('promo', ''));

        if ($input === '') {
            return [null, null];
        }

        $key = 'pricing-promo:'.$request->ip();

        if (RateLimiter::tooManyAttempts($key, 10)) {
            return [null, __('ui.pricing.promo_throttled')];
        }

        RateLimiter::hit($key, 3600);

        try {
            return [app(PromoCodeService::class)->preview($input), null];
        } catch (PromoCodeRejected $e) {
            return [null, $e->getMessage()];
        }
    }

    /**
     * Цена тарифа по промокоду — тем же расчётом, что и счёт
     * (OrderService::discounted): на витрине и в счёте сумма обязана
     * совпадать до сума.
     *
     * @param  array<string, mixed>  $promo
     * @return array{price_usd: float, price_uzs: int, discount_percent: int|null, days: int|null}
     */
    private static function promoPrice(Plan $plan, array $promo, float $rate): array
    {
        $percent = $promo['discount_percent'];

        return [
            'price_usd' => $percent === null ? 0.0 : round((float) $plan->price_usd * (100 - $percent) / 100, 2),
            'price_uzs' => $percent === null ? 0 : OrderService::discounted($plan->priceUzs($rate), $percent),
            'discount_percent' => $percent,
            'days' => $promo['days'],
        ];
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

        $showcase = $this->companiesByCountry();

        $countries = Country::listed()
            ->map(fn (Country $c): array => [
                'code' => $c->code,
                'name' => $c->name(),
                'companies' => (int) ($companyCounts[$c->id] ?? 0),
                'items' => $showcase[$c->id] ?? [],
            ])
            ->sortByDesc('companies')
            ->values();

        /*
         * Активные и запланированные — раздельно: заголовок «уже
         * работают» над восемью пустыми странами был неправдой
         * (аудит, п. 2.3). Пустая страна — это план, а не факт.
         */
        return Inertia::render('Countries', [
            'countries' => $countries->filter(fn (array $c): bool => $c['companies'] > 0)->values()->all(),
            'planned' => $countries->filter(fn (array $c): bool => $c['companies'] === 0)->values()->all(),
        ]);
    }

    /** Сколько компаний страны показывать сразу; остальные — по «Показать ещё». */
    private const COMPANIES_PER_COUNTRY = 12;

    /**
     * Все оставшиеся компании страны для кнопки «Показать ещё».
     *
     * Отдаёт JSON: страница стран сразу показывает только первые
     * компании, остальные подгружает одним нажатием — чтобы при
     * открытии не тянуть больше тысячи карточек.
     */
    public function countryCompanies(Request $request, string $code): JsonResponse
    {
        $country = Country::query()
            ->where('code', mb_strtolower($code))
            ->where('is_active', true)
            ->firstOrFail();

        $offset = max(0, (int) $request->query('offset', 0));

        $companies = $this->countryCompanyQuery()
            ->where('country_id', $country->id)
            ->orderByDesc('verification_level')
            ->orderByDesc('rating')
            ->orderBy('id')
            // OFFSET без LIMIT в SQL не пишется: берём с запасом «всё»
            ->offset($offset)
            ->limit(PHP_INT_MAX)
            ->get();

        return response()->json([
            'items' => $companies->map($this->countryCompanyCard(...))->values(),
        ]);
    }

    /**
     * Первая порция компаний под каждой страной на странице «Страны».
     *
     * Порядок тот же, что в каталоге компаний: сначала проверенные,
     * затем по рейтингу. Остальные подгружает «Показать ещё»
     * (countryCompanies). Отбор одним запросом через row_number:
     * компаний больше тысячи, и тянуть их все незачем.
     *
     * @return array<int, list<array<string, mixed>>> по country_id
     */
    private function companiesByCountry(): array
    {
        $ranked = Company::query()
            ->select('companies.*')
            ->selectRaw('row_number() over (partition by country_id order by verification_level desc, rating desc, id) as country_rank')
            // Счётчик — во внутреннем запросе: на подзапрос во FROM
            // withCount не навешивается
            ->withCount(['listings as listings_count' => fn ($q) => $q->where('status', Listing::STATUS_ACTIVE)])
            ->where('status', Company::STATUS_ACTIVE)
            ->whereNotNull('country_id');

        return Company::query()
            ->fromSub($ranked, 'companies')
            ->with(['city.translations'])
            ->where('country_rank', '<=', self::COMPANIES_PER_COUNTRY)
            ->orderBy('country_rank')
            ->get()
            ->groupBy('country_id')
            ->map(fn ($companies) => $companies->map($this->countryCompanyCard(...))->values()->all())
            ->all();
    }

    private function countryCompanyQuery(): Builder
    {
        return Company::query()
            ->with(['city.translations'])
            ->withCount(['listings as listings_count' => fn ($q) => $q->where('status', Listing::STATUS_ACTIVE)])
            ->where('status', Company::STATUS_ACTIVE);
    }

    /** @return array<string, mixed> */
    private function countryCompanyCard(Company $c): array
    {
        return [
            'slug' => $c->slug,
            'name' => $c->name,
            'type_label' => $c->typeLabel(),
            'city' => $c->city?->name(),
            'verification_level' => $c->verification_level,
            'rating' => (float) $c->rating,
            'listings_count' => (int) $c->listings_count,
            'initials' => $c->initials(),
            'logo' => $c->logoUrl(),
        ];
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

        /*
         * Партнёров назначает администратор (действие «Партнёрство»
         * в админке): это договорённость с площадкой, а не уровень
         * проверки. Две вкладки — генеральные и обычные партнёры.
         */
        $rows = Company::query()
            ->with(['city.translations', 'country.translations'])
            ->withCount(['listings as listings_count' => fn ($q) => $q->where('status', Listing::STATUS_ACTIVE)])
            ->where('status', Company::STATUS_ACTIVE)
            ->whereIn('partner_tier', array_keys(Company::PARTNER_TIERS))
            ->orderBy('partner_sort')
            ->orderByDesc('rating')
            ->orderBy('id')
            ->get();

        $present = fn (Company $c): array => [
            'slug' => $c->slug,
            'name' => $c->name,
            'type_label' => $c->typeLabel(),
            'city' => $c->city?->name(),
            'country' => $c->country?->name(),
            'verification_level' => $c->verification_level,
            'rating' => (float) $c->rating,
            'reviews_count' => $c->reviews_count,
            // Объявления вместо «сделок»: измеримая величина
            'listings_count' => (int) $c->listings_count,
            'initials' => $c->initials(),
            'logo' => $c->logoUrl(),
        ];

        return Inertia::render('Partners', [
            'general' => $rows->where('partner_tier', Company::PARTNER_GENERAL)->map($present)->values()->all(),
            'partners' => $rows->where('partner_tier', Company::PARTNER_REGULAR)->map($present)->values()->all(),
            'stats' => [
                'total' => Company::where('status', Company::STATUS_ACTIVE)->count(),
                'verified' => Company::where('status', Company::STATUS_ACTIVE)
                    ->where('verification_level', '>=', Company::VERIFICATION_COMPANY)
                    ->count(),
                'listings' => Listing::where('status', Listing::STATUS_ACTIVE)->count(),
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
     * Сделок здесь нет намеренно: площадка в расчётах не участвует
     * и считать их нечем — любое число было бы выдумкой (аудит, п. 2.1).
     *
     * @return array{companies: int, listings: int, categories: int, countries: int}
     */
    private function stats(): array
    {
        return [
            'companies' => Company::where('status', Company::STATUS_ACTIVE)->count(),
            'listings' => Listing::where('status', Listing::STATUS_ACTIVE)->visibleIn()->count(),
            // Считаем подкатегории: разделов верхнего уровня шесть,
            // и «6 категорий товаров» продаёт площадку хуже, чем есть
            'categories' => Category::where('is_active', true)->whereNotNull('parent_id')->count(),
            // Только страны, где есть хотя бы одна активная компания:
            // «9 стран» при восьми пустых — неправда на витрине
            'countries' => Country::where('is_active', true)
                ->whereHas('companies', fn ($q) => $q->where('status', Company::STATUS_ACTIVE))
                ->count(),
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
            ->visibleIn()
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

    /** Направления «Доп. услуг» по умолчанию, пока задач нет или их поровну. */
    private const DEFAULT_SERVICES = ['it', 'logistics'];

    /**
     * Две популярные услуги площадки для плитки «Популярные категории».
     *
     * Направления «Доп. услуг» (IT-услуги, логистика, подбор персонала…)
     * ранжируются по числу активных задач. «Другое» не показываем:
     * плитка «Другое» ничего не говорит о том, что за ней. Пока задач
     * мало, недостающие места занимают IT-услуги и логистика — плитки
     * видны всегда, это витрина раздела, а не счётчик.
     *
     * @return list<array{type: string, name: string, tasks: int}>
     */
    private function popularServices(): array
    {
        $counts = ItTask::query()
            ->active()
            ->whereHas('company', fn ($q) => $q->where('status', Company::STATUS_ACTIVE))
            ->selectRaw('service_type, count(*) as total')
            ->groupBy('service_type')
            ->pluck('total', 'service_type');

        $sections = array_diff(array_keys(ItTask::SERVICE_SECTIONS), ['other']);

        return collect($sections)
            ->map(fn (string $section): array => [
                'type' => $section,
                'name' => __('ui.it_tasks.types.'.$section),
                'tasks' => (int) collect(ItTask::typesUnder($section))->sum(fn (string $t): int => (int) ($counts[$t] ?? 0)),
            ])
            // При равенстве выше те, что по умолчанию, дальше — порядок разделов
            ->sortBy([
                ['tasks', 'desc'],
                fn (array $a, array $b): int => $this->defaultServiceRank($a['type']) <=> $this->defaultServiceRank($b['type']),
            ])
            ->take(2)
            ->values()
            ->all();
    }

    private function defaultServiceRank(string $section): int
    {
        $rank = array_search($section, self::DEFAULT_SERVICES, true);

        return $rank === false ? count(self::DEFAULT_SERVICES) : $rank;
    }

    /**
     * Лента товаров на главной — витрина тарифа VIP.
     *
     * Попадают только объявления компаний с действующей подпиской VIP:
     * место на первом экране продаётся вместе с тарифом, и разбавлять
     * его бесплатными объявлениями значит продавать пустоту. Компании
     * без VIP видны в каталоге, куда ведёт ссылка «Все товары».
     *
     * Условия действующей подписки повторены здесь, а не взяты из
     * связи subscription(): та построена на latestOfMany и в подзапросе
     * whereHas ведёт себя непредсказуемо.
     *
     * @return list<array<string, mixed>>
     */
    private function latestListings(): array
    {
        return Listing::query()
            ->with(ListingCard::relations())
            // Продвинутые (ТОП/Срочно) — всегда первыми: это оплаченное
            // место в ленте, покупатель платит именно за него
            ->withCount(['promotions as boosted' => fn ($q) => $q->where('status', 'active')])
            ->where('status', Listing::STATUS_ACTIVE)
            ->visibleIn()
            ->where('type', Listing::TYPE_SUPPLY)
            ->whereHas('company', fn ($q) => $q
                ->where('status', Company::STATUS_ACTIVE)
                ->whereHas('subscriptions', fn ($s) => $s
                    ->where('status', 'active')
                    ->where(fn ($alive) => $alive->whereNull('ends_at')->orWhere('ends_at', '>', now()))
                    ->whereRelation('plan', 'code', Plan::VIP)))
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
            ->visibleIn()
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
            ->withCount(['listings as listings_count' => fn ($q) => $q->where('status', Listing::STATUS_ACTIVE)])
            ->where('status', Company::STATUS_ACTIVE)
            ->orderByDesc('verification_level')
            ->orderByDesc('rating')
            ->orderBy('id')
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
                // Объявления вместо «сделок»: измеримая величина
                'listings_count' => (int) $c->listings_count,
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
                'body' => ContentTranslation::text($r->body),
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
        return Country::listed()
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
