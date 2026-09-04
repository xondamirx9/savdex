import { Link } from '@/components/ui/Link';
import { Check, X } from 'lucide-react';
import { formatNumber } from '@/components/cabinet';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

interface PricingPlan {
    code: string;
    name: string;
    price_uzs: number;
    price_usd: number;
    listings_limit: number | null;
    contacts_limit: number | null;
    responses_limit: number | null;
    promo_units: number;
    listing_days: number;
    verification_days: number;
    sees_interested_names: boolean;
    has_microsite: boolean;
    advanced_analytics: boolean;
}

/** Кому адресован тариф — витринная подпись, в базе ей не место. */
const NOTE_CODES = ['free', 'flash', 'business', 'premium', 'vip'];

/**
 * Пункты карточки собираются из лимитов тарифа — тех же, что в кабинете.
 * Подписи — из словаря: страница обязана говорить на языке посетителя,
 * как и весь каталог.
 */
function features(p: PricingPlan): [string, boolean][] {
    return [
        [
            p.listings_limit === null
                ? t('pricing.listings_unlimited')
                : tChoice('pricing.listings_count', p.listings_limit),
            true,
        ],
        [
            p.contacts_limit === null
                ? t('pricing.contacts_unlimited')
                : tChoice('pricing.contacts_count', p.contacts_limit),
            true,
        ],
        [
            p.responses_limit === null
                ? t('pricing.responses_unlimited')
                : p.responses_limit > 0
                  ? tChoice('pricing.responses_count', p.responses_limit)
                  : t('pricing.responses_off'),
            p.responses_limit === null || p.responses_limit > 0,
        ],
        [
            p.promo_units > 0 ? tChoice('pricing.promo_count', p.promo_units) : t('pricing.promo_off'),
            p.promo_units > 0,
        ],
        [tChoice('pricing.listing_days', p.listing_days), true],
        [tChoice('pricing.verification_days', p.verification_days), true],
        [t('pricing.sees_names'), p.sees_interested_names],
        [
            p.advanced_analytics ? t('pricing.microsite_analytics') : t('pricing.microsite'),
            p.has_microsite,
        ],
    ];
}

export default function Pricing({ plans }: { plans: PricingPlan[] }) {
    return (
        <PublicLayout title={t('seo.pricing_title')} description={t('seo.pricing_description')}>
            <section className="section--tight" style={{ background: 'var(--primary-50)' }}>
                <div className="container center">
                    {/* Заголовок обязан сходиться с тарифами ниже: лимиты
                        на число и срок объявлений — это тоже плата
                        за размещение, отрицать её нельзя (аудит, п. 4.4) */}
                    <h1 className="t-h1">{t('pricing.hero_title')}</h1>
                    <p className="t-lead mt-16" style={{ maxWidth: 640, marginLeft: 'auto', marginRight: 'auto' }}>
                        {t('pricing.hero_lead')}
                    </p>
                </div>
            </section>

            <section className="section">
                <div className="container">
                    <div className="grid grid-tight plan-grid">
                        {plans.map((p) => {
                            const highlighted = p.code === 'business';

                            return (
                                <div key={p.code} className={highlighted ? 'plan is-hi' : 'plan'}>
                                    {highlighted && <span className="plan-tag">{t('pricing.popular')}</span>}
                                    <h2 className="t-h3">{p.name}</h2>
                                    <p className="t-sm muted">
                                        {NOTE_CODES.includes(p.code) ? t(`pricing.note_${p.code}`) : ''}
                                    </p>
                                    <div className="plan-price">
                                        {formatNumber(p.price_uzs)} <small>{t('catalog.currency_uzs')}</small>
                                    </div>
                                    {/* Долларовый эквивалент: тариф задан в долларах,
                                        сумовая цена пересчитана по курсу ЦБ */}
                                    <p className="t-caption muted">
                                        {p.price_uzs > 0
                                            ? `${t('pricing.usd_approx', { price: formatNumber(p.price_usd) })} ${t('pricing.per_month')}`
                                            : t('pricing.forever')}
                                    </p>
                                    <ul>
                                        {features(p).map(([label, on]) => (
                                            <li key={label} className={on ? undefined : 'off'}>
                                                {on ? (
                                                    <Check aria-hidden className="size-4" />
                                                ) : (
                                                    <X aria-hidden className="size-4" />
                                                )}
                                                {label}
                                            </li>
                                        ))}
                                    </ul>
                                    <Link
                                        href={routes.register}
                                        className={`btn btn-block ${highlighted ? 'btn-primary' : 'btn-secondary'}`}
                                    >
                                        {t('pricing.choose')}
                                    </Link>
                                </div>
                            );
                        })}
                    </div>
                    <p className="center mt-24 t-sm muted">{t('pricing.payment_note')}</p>
                </div>
            </section>
        </PublicLayout>
    );
}
