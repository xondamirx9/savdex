<?php

declare(strict_types=1);

namespace App\Support\Microsite;

use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\CompanyDocument;
use App\Models\CompanySite;
use App\Models\Listing;
use App\Models\Review;
use App\Support\ListingCard;
use App\Support\Locales;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Страница мини-сайта — одна и для посетителей, и для предпросмотра
 * в кабинете. Две сборки разошлись бы на первом же новом блоке,
 * и компания видела бы в редакторе не то, что увидят клиенты.
 */
final class SitePage
{
    /** Сколько товаров показывать: мини-сайт — витрина, а не каталог. */
    private const LISTINGS = 24;

    /**
     * @param  array<string, string>  $theme  результат SiteTheme::normalize()
     */
    public static function render(CompanySite $site, array $theme, bool $preview = false): Response
    {
        $company = $site->company;
        $company->loadMissing(['city.translations', 'country.translations', 'publicContacts']);

        return Inertia::render('site/Show', [
            'theme' => $theme,
            'vars' => SiteTheme::variables($theme),
            'fonts' => SiteTheme::fontsUrl($theme),
            'preview' => $preview,
            'site' => [
                'url' => $site->url(),
                // Карточка на площадке — для отметки «Мы на SAVDEX»
                'marketplace' => self::marketplaceUrl('/company/'.$company->slug),
            ],
            'company' => $company->businessCard(),
            'initials' => $company->initials(),
            'contacts' => self::contacts($company),
            'listings' => self::listings($company),
            'files' => self::files($company),
            'reviews' => self::reviews($company),
        ])
            ->rootView('microsite')
            ->withViewData([
                'siteCss' => SiteTheme::css($theme),
                'siteFonts' => SiteTheme::fontsUrl($theme),
                'siteTitle' => $company->name,
                'siteDescription' => str($company->description ?? '')->squish()->limit(160)->toString(),
                'siteIcon' => $company->logoUrl(),
                'siteCanonical' => $site->url(),
                // Предпросмотр черновика в поиск попадать не должен
                'siteNoindex' => $preview,
            ]);
    }

    /**
     * Контакты открыты целиком.
     *
     * На карточке площадки за них платит покупатель, но мини-сайт —
     * собственная страница компании, оплаченная её тарифом. Сайт,
     * на котором телефон компании спрятан под замок, ей не нужен,
     * и покупать такой тариф никто бы не стал.
     *
     * @return list<array<string, mixed>>
     */
    private static function contacts(Company $company): array
    {
        return $company->publicContacts
            ->map(fn (CompanyContact $c): array => [
                'type' => $c->type,
                'label' => $c->label,
                'contact_person' => $c->contact_person,
                'value' => $c->value,
                'href' => $c->href(),
            ])
            ->values()
            ->all();
    }

    /** @return list<array<string, mixed>> */
    private static function listings(Company $company): array
    {
        return $company->activeListings()
            ->visibleIn()
            ->with(ListingCard::relations())
            ->latest('published_at')
            ->limit(self::LISTINGS)
            ->get()
            ->map(function (Listing $l): array {
                $card = ListingCard::present($l);

                return [
                    'id' => $card['id'],
                    'title' => $card['title'],
                    'excerpt' => $card['excerpt'],
                    'type' => $card['type'],
                    'cover' => $card['cover'],
                    'price' => $card['price'],
                    'currency' => $card['currency'],
                    'unit' => $card['unit'],
                    'negotiable' => $card['negotiable'],
                    'min_order' => $card['min_order'],
                    'category' => $card['category'],
                    // Подробности — на площадке: там фотографии, характеристики
                    // и отклик. Своей страницы товара у мини-сайта пока нет
                    'url' => $l->slug !== null ? self::marketplaceUrl('/listing/'.$l->slug) : null,
                ];
            })
            ->values()
            ->all();
    }

    /**
     * Документы и фотографии, которые компания показывает на карточке.
     * Правило то же, что на визитке: непроверенный документ не виден.
     *
     * @return list<array<string, mixed>>
     */
    private static function files(Company $company): array
    {
        return $company->documents()
            ->where('is_public', true)
            ->get()
            ->filter(fn (CompanyDocument $d): bool => $d->isVisibleOnCard() && ! $d->fileMissing())
            ->map(fn (CompanyDocument $d): array => [
                'id' => $d->id,
                'title' => $d->title,
                'is_image' => $d->isImage(),
                'type_label' => $d->typeLabel(),
                'size' => $d->sizeLabel(),
                // Относительный адрес: скачивание открыто и на домене
                // мини-сайтов (см. RestrictSiteHost)
                'url' => '/files/'.$d->id,
            ])
            ->values()
            ->all();
    }

    /** @return array{rating: float, count: int, latest: list<array<string, mixed>>} */
    private static function reviews(Company $company): array
    {
        return [
            'rating' => (float) $company->rating,
            'count' => (int) $company->reviews_count,
            'latest' => $company->reviews()
                ->with('authorCompany')
                ->latest()
                ->limit(6)
                ->get()
                ->map(fn (Review $r): array => [
                    'id' => $r->id,
                    'author' => $r->authorCompany?->name ?? __('ui.cabinet.incoming.deleted'),
                    'rating' => $r->rating,
                    'body' => $r->body,
                    'when' => $r->created_at->translatedFormat('d.m.Y'),
                ])
                ->values()
                ->all(),
        ];
    }

    /** Адрес на площадке, на языке посетителя. */
    private static function marketplaceUrl(string $path): string
    {
        return rtrim((string) config('app.url'), '/').Locales::prefix(app()->getLocale()).$path;
    }
}
