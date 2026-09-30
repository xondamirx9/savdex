import { router, usePage } from '@inertiajs/react';
import { BadgeCheck, Building2, Clock, Heart, MapPin, Package, ShoppingCart, Star } from 'lucide-react';
import { Link } from '@/components/ui/Link';
import { formatNumber } from '@/components/cabinet';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { unitLabel } from '@/lib/units';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

/**
 * Карточка товара — одна на все ленты: «Новые объявления» главной,
 * каталог и избранное. Фотография, метка NEW, флаг страны, цена
 * «от … / ед.» и минимальная партия — как в макете новой витрины.
 */

export interface ProductRow {
    id: number;
    slug: string | null;
    title: string;
    excerpt?: string;
    cover: string | null;
    photos: number;
    type: 'supply' | 'demand';
    category: string | null;
    price: number | null;
    currency: string;
    /** Приблизительно в валюте языка; null — пересчитывать нечего */
    converted: Money | null;
    unit: string | null;
    negotiable: boolean;
    min_order: number | null;
    city: string | null;
    country: string | null;
    country_name: string | null;
    published: string | null;
    is_new: boolean;
    views: number;
    company: {
        name: string | null;
        slug: string | null;
        verified: number;
        rating: number;
        trust: number;
        /** За сколько часов компания обычно отвечает; null — не измеряли */
        response_hours: number | null;
        /** Заявка площадки: подписана SavdEx, а не служебной компанией */
        platform?: boolean;
    };
    badges: string[];
    promoted: boolean;
    /** false на странице избранного, если объявление снято с публикации */
    active?: boolean;
}

export interface Money {
    price: number;
    currency: string;
}

/** Знак валюты перед числом — как пишут прайсы: $95, €80. */
const SYMBOLS: Record<string, string> = { USD: '$', EUR: '€', RUB: '₽', CNY: '¥', TRY: '₺' };

export function money(price: number, currency: string): string {
    const symbol = SYMBOLS[currency];

    if (symbol) return `${symbol}${formatNumber(price)}`;

    return `${formatNumber(price)} ${currency === 'UZS' ? t('catalog.currency_uzs') : currency}`;
}

/**
 * Цена на витрине: в валюте языка, если она пересчитана.
 *
 * Пересчёт по курсу ЦБ приблизителен, поэтому со знаком «≈»; цена
 * продавца остаётся рядом (sellerPrice) — договор заключают по ней.
 */
export function shownPrice(price: number, currency: string, converted: Money | null): string {
    return converted ? `≈ ${money(converted.price, converted.currency)}` : money(price, currency);
}

/** Подпись «Цена продавца: …» — только когда показан пересчёт. */
export function sellerPrice(price: number, currency: string, converted: Money | null): string | null {
    return converted ? t('catalog.seller_price', { price: money(price, currency) }) : null;
}

/**
 * Сердечко избранного.
 *
 * Кнопка, а не ссылка: нажатие не должно открывать карточку.
 * Гость отправляется на вход — избранное живёт в аккаунте.
 */
function FavButton({ id }: { id: number }) {
    const { auth, favorites } = usePage<SharedProps>().props;
    const pressed = (favorites ?? []).includes(id);

    return (
        <button
            type="button"
            className="product-fav"
            aria-pressed={pressed}
            aria-label={pressed ? t('favorites.remove') : t('favorites.add')}
            onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();

                if (!auth?.user) {
                    router.visit(routes.login);

                    return;
                }

                router.post(routes.favoriteToggle(id), {}, { preserveScroll: true, preserveState: true });
            }}
        >
            <Heart aria-hidden className="size-4" />
        </button>
    );
}

export function ProductCard({ row }: { row: ProductRow }) {
    const href = row.slug ? routes.listing(row.slug) : routes.catalog;
    const TypeIcon = row.type === 'demand' ? ShoppingCart : Package;

    return (
        /* Неактивная карточка приглушается, но НЕ через .is-disabled:
           pointer-events:none заблокировал бы сердечко, и снятое
           с публикации объявление нельзя было бы убрать из избранного */
        <article className={cn('product-card', row.promoted && 'is-promoted', row.active === false && 'is-inactive')}>
            <Link href={href} className="product-media" tabIndex={-1} aria-hidden>
                {row.cover ? (
                    /* alt с названием: трафик из Google Картинок
                       и доступность — пустой alt терял и то, и другое */
                    <img src={row.cover} alt={row.title} loading="lazy" />
                ) : (
                    <span className="product-media-ph">
                        <TypeIcon aria-hidden className="size-10" />
                    </span>
                )}
                <span className="product-flags">
                    {row.is_new && <span className="badge-new">{t('catalog.badge_new')}</span>}
                    {row.type === 'demand' && (
                        <span className="badge badge-demand">{t('catalog.badge_demand')}</span>
                    )}
                    {row.badges.map((b) => (
                        <span key={b} className="badge badge-top">
                            {b}
                        </span>
                    ))}
                </span>
            </Link>

            <FavButton id={row.id} />

            <div className="product-body">
                <Link href={href} className="product-title">
                    {row.title}
                </Link>

                <span className="product-price">
                    {row.negotiable || row.price === null ? (
                        <small>{t('catalog.price_negotiable')}</small>
                    ) : (
                        <>
                            {shownPrice(row.price, row.currency, row.converted)}
                            {row.unit && <small> / {unitLabel(row.unit)}</small>}
                        </>
                    )}
                </span>

                {/* Пересчёт приблизителен — цена продавца остаётся
                    на карточке: договор заключают по ней */}
                {!row.negotiable && row.price !== null && row.converted && (
                    <span className="product-seller-price">
                        {sellerPrice(row.price, row.currency, row.converted)}
                    </span>
                )}

                {/* Строки-факты: то, что покупатель сверяет до перехода
                    в карточку, — партия, город, проверка, скорость
                    ответа. Каждая строка появляется только со своими
                    данными: пустая строка со значком хуже её отсутствия */}
                <ul className="product-facts">
                    {row.min_order !== null && (
                        <li>
                            <Package aria-hidden className="size-4" />
                            {t('catalog.moq_label')}: {formatNumber(row.min_order)}
                            {row.unit ? ` ${unitLabel(row.unit)}` : ''}
                        </li>
                    )}

                    {(row.city || row.country_name) && (
                        <li>
                            <MapPin aria-hidden className="size-4" />
                            {row.city ?? row.country_name}
                        </li>
                    )}

                    {row.company.verified >= 2 && (
                        <li className="is-verified">
                            <BadgeCheck aria-hidden className="size-4" />
                            {t('catalog.verified_seller')}
                        </li>
                    )}

                    {row.company.response_hours !== null && row.company.response_hours > 0 && (
                        <li>
                            <Clock aria-hidden className="size-4" />
                            {t('catalog.responds_in', { hours: String(row.company.response_hours) })}
                        </li>
                    )}

                    <li className="product-facts-company">
                        <Building2 aria-hidden className="size-4" />
                        {/* Имя собственное: браузерный переводчик превращал
                            «OOO Tranquil» в «ООО Спокойствие» */}
                        <b className="notranslate" translate="no">{row.company.name}</b>
                        {row.company.platform && <span className="muted">· {t('catalog.platform_badge')}</span>}
                        {row.company.rating > 0 && (
                            <span className="listing-rating">
                                <Star aria-hidden className="size-3" style={{ fill: 'currentColor', color: 'var(--warning)' }} />
                                {row.company.rating.toFixed(1)}
                            </span>
                        )}
                    </li>
                </ul>

                {/* Кнопка — оформление, а не вторая ссылка: вся карточка
                    и так ведёт в объявление (a.product-title::after).
                    Отдельная ссылка удвоила бы обход с клавиатуры
                    и список ссылок у скринридера */}
                <span className="product-cta" aria-hidden>
                    {t('catalog.open_offer')}
                </span>
            </div>
        </article>
    );
}
