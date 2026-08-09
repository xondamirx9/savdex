<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Company;
use App\Models\Listing;

/**
 * Готовые описания страниц для поиска.
 *
 * Собраны в одном месте, а не разбросаны по контроллерам: заголовки
 * должны строиться по одному правилу, иначе выдача выглядит как набор
 * разных сайтов. Правило такое — сначала то, что человек искал, потом
 * уточнение, и только в конце название площадки (его добавляет
 * Seo::getTitle()).
 */
class SeoBuilders
{
    public function __construct(private readonly Seo $seo) {}

    /** Карточка объявления — главная посадочная страница площадки. */
    public function listing(Listing $listing): void
    {
        $company = $listing->company;
        $city = $company?->city?->name();

        $price = $listing->price_negotiable || $listing->price === null
            ? 'цена договорная'
            : number_format((float) $listing->price, 0, ',', ' ').' '.($listing->currency === 'UZS' ? 'сум' : $listing->currency);

        $this->seo
            ->title($listing->title.($city !== null ? " — {$city}" : ''))
            ->description($listing->description ?: "{$listing->title}. {$price}. Поставщик: {$company?->name}.")
            ->canonical(url('/listing/'.$listing->slug))
            ->image($listing->images->first()?->url())
            ->type('product')
            ->schema($this->productSchema($listing, $company))
            ->schema($this->breadcrumbs([
                'Каталог' => url('/catalog'),
                $listing->category?->name() ?? 'Объявления' => $listing->category_id !== null
                    ? url('/catalog?category='.$listing->category_id)
                    : url('/catalog'),
                $listing->title => url('/listing/'.$listing->slug),
            ]));
    }

    /**
     * Товар со сведениями о продавце.
     *
     * Эта разметка даёт в выдаче цену и наличие рядом со ссылкой —
     * для товарной площадки это заметная часть кликов.
     *
     * @return array<string, mixed>
     */
    private function productSchema(Listing $listing, ?Company $company): array
    {
        $schema = [
            '@type' => 'Product',
            'name' => $listing->title,
            'description' => (string) $listing->description,
            'category' => $listing->category?->name(),
            'image' => $listing->images->map(fn ($i): string => $i->url())->values()->all(),
        ];

        /*
         * Предложение указывается только с ценой: Offer без цены
         * поисковик считает неполным и разметку не показывает вовсе.
         * Договорная цена — честный случай «предложения нет».
         */
        if ($listing->price !== null && ! $listing->price_negotiable) {
            $schema['offers'] = [
                '@type' => 'Offer',
                'price' => (float) $listing->price,
                'priceCurrency' => $listing->currency,
                'availability' => 'https://schema.org/InStock',
                'url' => url('/listing/'.$listing->slug),
                'seller' => ['@type' => 'Organization', 'name' => $company?->name],
            ];
        }

        return $schema;
    }

    /** Визитка компании. */
    public function company(Company $company): void
    {
        $city = $company->city?->name();

        $fallback = trim(implode(', ', array_filter([
            $company->typeLabel(),
            $city,
            $company->tin !== null ? "ИНН {$company->tin}" : null,
        ])));

        $this->seo
            ->title($company->name.($city !== null ? " — {$city}" : ''))
            ->description($company->description ?: $fallback.'. Контакты, объявления и отзывы на SAVDEX.')
            ->canonical(url('/company/'.$company->slug))
            ->image($company->logoUrl())
            ->type('profile')
            ->schema($this->organizationSchema($company))
            ->schema($this->breadcrumbs([
                'Компании' => url('/companies'),
                $company->name => url('/company/'.$company->slug),
            ]));
    }

    /** @return array<string, mixed> */
    private function organizationSchema(Company $company): array
    {
        $schema = [
            '@type' => 'Organization',
            'name' => $company->name,
            'legalName' => $company->legal_name,
            'url' => url('/company/'.$company->slug),
            'logo' => $company->logoUrl(),
            'description' => $company->description,
            'taxID' => $company->tin,
            'foundingDate' => $company->founded_year !== null ? (string) $company->founded_year : null,
        ];

        if ($company->city !== null || $company->address !== null) {
            $schema['address'] = array_filter([
                '@type' => 'PostalAddress',
                'addressLocality' => $company->city?->name(),
                'addressCountry' => $company->country?->code !== null ? strtoupper($company->country->code) : null,
                'streetAddress' => $company->address,
            ]);
        }

        /*
         * Рейтинг показывается только при отзывах. Разметка с нулевой
         * оценкой и нулём отзывов — это заявка на звёзды в выдаче,
         * за которой ничего не стоит, и поисковики за такое понижают.
         */
        if ($company->reviews_count > 0) {
            $schema['aggregateRating'] = [
                '@type' => 'AggregateRating',
                'ratingValue' => round((float) $company->rating, 1),
                'reviewCount' => $company->reviews_count,
                'bestRating' => 5,
                'worstRating' => 1,
            ];
        }

        return array_filter($schema, fn ($v): bool => $v !== null && $v !== '');
    }

    /**
     * Каталог: заголовок собирается из выбранных фильтров.
     *
     * «Цемент оптом в Ташкенте» — то, что человек набирает в поиске;
     * «Каталог объявлений» — то, что он не набирает никогда.
     *
     * @param  array{query: string|null, category: string|null, city: string|null}  $context
     */
    public function catalog(array $context, int $total, bool $filtered): void
    {
        $subject = $context['query'] ?: $context['category'] ?: __('ui.seo.catalog_subject');

        $where = $context['city'] !== null
            ? __('ui.seo.catalog_in_city', ['city' => $context['city']])
            : __('ui.seo.catalog_in_country');

        $this->seo
            ->title($subject.$where)
            ->description(__('ui.seo.catalog_description', [
                'subject' => $subject,
                'where' => $where,
                'total' => $total,
            ]))
            ->canonical(url('/catalog'))
            /*
             * Страницы с фильтрами закрыты от индексации.
             *
             * Комбинации категорий, городов и запросов дают тысячи
             * адресов с почти одинаковым содержимым: они конкурируют
             * друг с другом и с самим каталогом за одни и те же запросы.
             * Ссылки при этом остаются проходимыми — карточки объявлений
             * роботу нужны.
             */
            ->noindex($filtered);
    }

    /** Каталог компаний. */
    public function companies(int $total, bool $filtered): void
    {
        $this->seo
            ->title(__('ui.seo.companies_title'))
            ->description(__('ui.seo.companies_description', ['total' => $total]))
            ->canonical(url('/companies'))
            ->noindex($filtered);
    }

    /** @param array<string, string> $crumbs подпись => адрес */
    private function breadcrumbs(array $crumbs): array
    {
        $items = [];
        $position = 1;

        foreach ($crumbs as $name => $url) {
            $items[] = [
                '@type' => 'ListItem',
                'position' => $position++,
                'name' => $name,
                'item' => $url,
            ];
        }

        return ['@type' => 'BreadcrumbList', 'itemListElement' => $items];
    }
}
