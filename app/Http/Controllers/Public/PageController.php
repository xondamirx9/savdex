<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Category;
use App\Models\Company;
use App\Models\Country;
use App\Models\Listing;
use App\Support\ListingCard;
use App\Support\NewsRepository;
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

        return Inertia::render('Home', [
            'stats' => $stats,
            'categories' => $this->popularCategories(),
            // Свежие объявления — лента «Новые объявления» первого экрана
            'latest' => $this->latestListings(),
            'countries' => $this->countryOptions(),
            // Три свежих новости прямо на главной: раздел, до которого
            // нужно ещё дойти по меню, читают в разы меньше
            'news' => $news->latest(3),
        ]);
    }

    public function about(): Response
    {
        app(Seo::class)
            ->title(__('ui.seo.about_title'))
            ->description(__('ui.seo.about_description'))
            ->canonical(url('/about'));

        return Inertia::render('About', ['stats' => $this->stats()]);
    }

    public function pricing(): Response
    {
        app(Seo::class)
            ->title(__('ui.seo.pricing_title'))
            ->description(__('ui.seo.pricing_description'))
            ->canonical(url('/pricing'));

        return Inertia::render('Pricing');
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
            ->all();
    }

    /** @return list<array<string, mixed>> */
    private function latestListings(): array
    {
        return Listing::query()
            ->with(ListingCard::relations())
            ->where('status', Listing::STATUS_ACTIVE)
            ->whereHas('company', fn ($q) => $q->where('status', Company::STATUS_ACTIVE))
            ->latest('published_at')
            ->limit(8)
            ->get()
            ->map(fn (Listing $l): array => ListingCard::present($l))
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
}
