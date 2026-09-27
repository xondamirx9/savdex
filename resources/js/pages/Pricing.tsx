import { router, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Check, Ticket, X } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { formatNumber } from '@/components/cabinet';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

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
    /** Цена по введённому промокоду — только у тарифа, на который он выпущен. */
    promo_price: {
        price_usd: number;
        price_uzs: number;
        discount_percent: number | null;
        days: number | null;
    } | null;
}

interface PricingPromo {
    code: string;
    plan_code: string;
    discount_percent: number | null;
    days: number | null;
}

/**
 * Перезагрузить страницу с кодом (или без него).
 *
 * Адрес берётся текущий, а не routes.pricing: на /uz/pricing запрос
 * без языкового префикса ушёл бы через редирект, и код из адреса
 * мог потеряться по дороге.
 */
function reloadWithPromo(code: string | null, onFinish?: () => void) {
    router.get(window.location.pathname, code ? { promo: code } : {}, {
        preserveScroll: true,
        preserveState: true,
        replace: true,
        only: ['plans', 'promo', 'promoError'],
        onFinish,
    });
}

/**
 * Ввод промокода. Код здесь только проверяется и пересчитывает цену
 * на карточке тарифа — гасится он в кабинете, когда компания выбирает
 * тариф: у гостя компании ещё нет, а цена ему нужна уже сейчас.
 */
function PromoBox({ promo, error, plans }: { promo: PricingPromo | null; error: string | null; plans: PricingPlan[] }) {
    const [open, setOpen] = useState(error !== null);
    const [code, setCode] = useState('');
    const [checking, setChecking] = useState(false);

    function submit(e: FormEvent) {
        e.preventDefault();

        if (code.trim() === '') {
            return;
        }

        setChecking(true);
        reloadWithPromo(code.trim(), () => setChecking(false));
    }

    if (promo !== null) {
        const planName = plans.find((p) => p.code === promo.plan_code)?.name ?? promo.plan_code;

        return (
            <div className="pricing-promo is-applied" role="status">
                <Ticket aria-hidden className="size-4" />
                <span>
                    {promo.discount_percent !== null
                        ? t('pricing.promo_applied_discount', {
                              code: promo.code,
                              percent: promo.discount_percent,
                              plan: planName,
                          })
                        : t('pricing.promo_applied_free', {
                              code: promo.code,
                              plan: planName,
                              days: tChoice('pricing.promo_days', promo.days ?? 0),
                          })}
                </span>
                <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                        setCode('');
                        setOpen(false);
                        reloadWithPromo(null);
                    }}
                >
                    {t('pricing.promo_remove')}
                </button>
            </div>
        );
    }

    if (!open) {
        return (
            <button type="button" className="btn btn-secondary mt-24" onClick={() => setOpen(true)}>
                <Ticket aria-hidden className="size-4" />
                {t('pricing.promo_open')}
            </button>
        );
    }

    return (
        <form onSubmit={submit} className="pricing-promo" noValidate>
            <div className={error ? 'field is-error' : 'field'} style={{ flex: '1 1 240px', minWidth: 0 }}>
                <label className="sr-only" htmlFor="pricing-promo">
                    {t('pricing.promo_label')}
                </label>
                <input
                    id="pricing-promo"
                    className="input"
                    name="promo"
                    placeholder={t('pricing.promo_placeholder')}
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={32}
                    autoFocus
                    value={code}
                    onChange={(e) => setCode(e.target.value.toUpperCase())}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? 'pricing-promo-error' : undefined}
                />
                {error && (
                    <p id="pricing-promo-error" className="text-danger mt-1.5 text-[13px]" style={{ textAlign: 'left' }}>
                        {error}
                    </p>
                )}
            </div>
            <button type="submit" className="btn btn-primary" disabled={checking || code.trim() === ''}>
                {checking ? t('pricing.promo_checking') : t('pricing.promo_apply')}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
                {t('pricing.promo_cancel')}
            </button>
        </form>
    );
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

/**
 * Куда ведёт «Выбрать».
 *
 * Вошедший — в кабинет, на оплату выбранного тарифа. Гость — на
 * регистрацию, которая запоминает тариф: после подтверждения почты
 * человек попадает на ту же оплату. Бесплатный тариф не покупают:
 * вошедшему он открывает кабинетный раздел тарифов, гостю — регистрацию.
 */
function chooseHref(code: string, signedIn: boolean): string {
    const paid = code !== 'free';

    if (signedIn) return paid ? `${routes.cabinetBilling}?plan=${code}` : routes.cabinetBilling;

    return paid ? `${routes.register}?plan=${code}` : routes.register;
}

export default function Pricing({
    plans,
    promo = null,
    promoError = null,
}: {
    plans: PricingPlan[];
    promo?: PricingPromo | null;
    promoError?: string | null;
}) {
    const signedIn = Boolean(usePage<SharedProps>().props.auth?.user);

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
                    <PromoBox promo={promo} error={promoError} plans={plans} />
                </div>
            </section>

            <section className="section">
                <div className="container">
                    <div className="grid grid-tight plan-grid">
                        {plans.map((p) => {
                            // С промокодом выделяется тариф, на который он выпущен
                            const highlighted = promo !== null ? p.promo_price !== null : p.code === 'business';

                            return (
                                <div key={p.code} className={highlighted ? 'plan is-hi' : 'plan'}>
                                    {highlighted && p.promo_price === null && (
                                        <span className="plan-tag">{t('pricing.popular')}</span>
                                    )}
                                    {p.promo_price !== null && (
                                        <span className="plan-tag">
                                            {p.promo_price.discount_percent !== null
                                                ? `−${p.promo_price.discount_percent}%`
                                                : t('pricing.promo_label')}
                                        </span>
                                    )}
                                    <h2 className="t-h3">{p.name}</h2>
                                    <p className="t-sm muted">
                                        {NOTE_CODES.includes(p.code) ? t(`pricing.note_${p.code}`) : ''}
                                    </p>
                                    {/* Доллар — основная цена: тариф задан в долларах
                                        и от курса не зависит. Сумовая цена —
                                        пересчёт по курсу ЦБ — идёт второй строкой:
                                        платят-то в сумах, и обе цифры нужны */}
                                    {p.promo_price !== null ? (
                                        <>
                                            {/* Цена по промокоду: прежняя остаётся видна
                                                зачёркнутой — иначе скидку не с чем сравнить */}
                                            <div className="plan-price is-promo">
                                                ${formatNumber(p.promo_price.price_usd)}
                                                <s className="plan-price-old">${formatNumber(p.price_usd)}</s>
                                            </div>
                                            <p className="plan-price-alt">
                                                {formatNumber(p.promo_price.price_uzs)} {t('catalog.currency_uzs')}
                                            </p>
                                            <p className="t-caption plan-promo-note">
                                                {p.promo_price.discount_percent !== null
                                                    ? `−${p.promo_price.discount_percent}% · ${t('pricing.per_month')}`
                                                    : t('pricing.promo_free', {
                                                          days: tChoice('pricing.promo_days', p.promo_price.days ?? 0),
                                                      })}
                                            </p>
                                        </>
                                    ) : (
                                        <>
                                            <div className="plan-price">${formatNumber(p.price_usd)}</div>
                                            <p className="plan-price-alt">
                                                {formatNumber(p.price_uzs)} {t('catalog.currency_uzs')}
                                            </p>
                                            <p className="t-caption muted">
                                                {p.price_uzs > 0 ? t('pricing.per_month') : t('pricing.forever')}
                                            </p>
                                        </>
                                    )}
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
                                    {p.promo_price !== null && promo !== null ? (
                                        /* Код гасится в кабинете: туда и ведём, с кодом
                                           в поле. Гостя вход вернёт на эту же страницу */
                                        <>
                                            <Link
                                                href={`${routes.cabinetBilling}?promo=${encodeURIComponent(promo.code)}`}
                                                className="btn btn-block btn-primary"
                                            >
                                                {t('pricing.promo_activate')}
                                            </Link>
                                            <p className="t-caption muted mt-8">{t('pricing.promo_hint')}</p>
                                        </>
                                    ) : (
                                        <Link
                                            href={chooseHref(p.code, signedIn)}
                                            className={`btn btn-block ${highlighted ? 'btn-primary' : 'btn-secondary'}`}
                                        >
                                            {t('pricing.choose')}
                                        </Link>
                                    )}
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
