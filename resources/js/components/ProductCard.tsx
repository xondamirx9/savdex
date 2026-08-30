import { router, usePage } from '@inertiajs/react';
import { Heart, Package, ShoppingCart, Star } from 'lucide-react';
import { Link } from '@/components/ui/Link';
import { formatNumber } from '@/components/cabinet';
import { cn } from '@/lib/cn';
import { flag } from '@/lib/flag';
import { t } from '@/lib/i18n';
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
    unit: string | null;
    negotiable: boolean;
    min_order: number | null;
    city: string | null;
    country: string | null;
    country_name: string | null;
    published: string | null;
    is_new: boolean;
    views: number;
    company: { name: string | null; slug: string | null; verified: number; rating: number; trust: number };
    badges: string[];
    promoted: boolean;
    /** false на странице избранного, если объявление снято с публикации */
    active?: boolean;
}

/** Знак валюты перед числом — как пишут прайсы: $95, €80. */
const SYMBOLS: Record<string, string> = { USD: '$', EUR: '€', RUB: '₽', CNY: '¥', TRY: '₺' };

export function money(price: number, currency: string): string {
    const symbol = SYMBOLS[currency];

    if (symbol) return `${symbol}${formatNumber(price)}`;

    return `${formatNumber(price)} ${currency === 'UZS' ? t('catalog.currency_uzs') : currency}`;
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
    const countryFlag = flag(row.country);

    return (
        /* Неактивная карточка приглушается, но НЕ через .is-disabled:
           pointer-events:none заблокировал бы сердечко, и снятое
           с публикации объявление нельзя было бы убрать из избранного */
        <article className={cn('product-card', row.promoted && 'is-promoted', row.active === false && 'is-inactive')}>
            <Link href={href} className="product-media" tabIndex={-1} aria-hidden>
                {row.cover ? (
                    <img src={row.cover} alt="" loading="lazy" />
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
                <span className="product-origin">
                    {countryFlag && (
                        <span className="flag" aria-hidden>
                            {countryFlag}
                        </span>
                    )}
                    {row.country_name ?? row.city ?? ''}
                    <span
                        className={cn(
                            'product-trust',
                            row.company.trust >= 70 && 'is-high',
                            row.company.trust < 40 && 'is-low',
                        )}
                        title={t('catalog.trust_hint')}
                    >
                        {t('catalog.trust', { percent: String(row.company.trust) })}
                    </span>
                </span>

                <Link href={href} className="product-title">
                    {row.title}
                </Link>

                <div className="product-price-row">
                    <span className="product-price">
                        {row.negotiable || row.price === null ? (
                            <small>{t('catalog.price_negotiable')}</small>
                        ) : (
                            <>
                                {/* Шаблон «от :price» лежит в словаре целиком:
                                    в узбекском и китайском «от» стоит после числа */}
                                {t('catalog.price_from', { price: money(row.price, row.currency) })}
                                {row.unit && <small> / {row.unit}</small>}
                            </>
                        )}
                    </span>
                    {row.min_order !== null && (
                        <span className="product-moq">
                            {t('catalog.moq')}: {formatNumber(row.min_order)}
                            {row.unit ? ` ${row.unit}` : ''}
                        </span>
                    )}
                </div>

                <span className="product-company">
                    <b>{row.company.name}</b>
                    {row.company.verified >= 2 && (
                        <span title={t('catalog.verified')} style={{ color: 'var(--success)', display: 'inline-flex' }}>
                            <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M9 12l2 2 4-4" />
                                <circle cx="12" cy="12" r="9" />
                            </svg>
                        </span>
                    )}
                    {row.company.rating > 0 && (
                        <span className="listing-rating">
                            <Star aria-hidden className="size-3" style={{ fill: 'currentColor', color: 'var(--warning)' }} />
                            {row.company.rating.toFixed(1)}
                        </span>
                    )}
                </span>
            </div>
        </article>
    );
}
