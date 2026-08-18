import { Link } from '@/components/ui/Link';
import { Check, X } from 'lucide-react';
import { formatNumber } from '@/components/cabinet';
import { PublicLayout } from '@/layouts/PublicLayout';
import { routes } from '@/routes';

interface PricingPlan {
    code: string;
    name: string;
    price_uzs: number;
    listings_limit: number | null;
    contacts_limit: number | null;
    promo_units: number;
    listing_days: number;
    has_microsite: boolean;
    advanced_analytics: boolean;
}

/** Кому адресован тариф — витринная подпись, в базе ей не место. */
const NOTES: Record<string, string> = {
    free: 'Попробовать площадку',
    flash: 'Небольшая компания',
    business: 'Оптовик и производитель',
    premium: 'Максимальная видимость',
    vip: 'Всё включено, максимум охвата',
};

/** Русское склонение: 4 объявления, 15 объявлений, 50 контактов. */
function plural(n: number, one: string, few: string, many: string): string {
    const mod10 = n % 10;
    const mod100 = n % 100;

    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;

    return many;
}

/** Пункты карточки собираются из лимитов тарифа — тех же, что в кабинете. */
function features(p: PricingPlan): [string, boolean][] {
    return [
        [
            p.listings_limit === null
                ? 'Объявления без ограничений'
                : `${p.listings_limit} активных ${plural(p.listings_limit, 'объявление', 'объявления', 'объявлений')}`,
            true,
        ],
        [
            p.contacts_limit === null
                ? 'Контакты без ограничений'
                : `${p.contacts_limit} ${plural(p.contacts_limit, 'контакт', 'контакта', 'контактов')} в месяц`,
            true,
        ],
        [p.promo_units > 0 ? `${p.promo_units} продвижений в месяц` : 'Продвижение', p.promo_units > 0],
        [`Срок показа ${p.listing_days} дней`, true],
        [
            p.advanced_analytics ? 'Мини-сайт и расширенная аналитика' : 'Мини-сайт компании',
            p.has_microsite,
        ],
    ];
}

export default function Pricing({ plans }: { plans: PricingPlan[] }) {
    return (
        <PublicLayout
            title="Тарифы"
            description="Размещение объявлений бесплатно. Тарифы Free, Flash, Business, Premium и VIP. Оплата Uzcard, Humo, Visa и Mastercard."
        >
            <section className="section--tight" style={{ background: 'var(--primary-50)' }}>
                <div className="container center">
                    <h1 className="t-h1">Платите за результат, а не за размещение</h1>
                    <p className="t-lead mt-16" style={{ maxWidth: 640, marginLeft: 'auto', marginRight: 'auto' }}>
                        Публиковать объявления бесплатно на любом тарифе. Деньги берём только за доступ к контактам
                        и за видимость в выдаче.
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
                                    {highlighted && <span className="plan-tag">Выбирают чаще всего</span>}
                                    <h2 className="t-h3">{p.name}</h2>
                                    <p className="t-sm muted">{NOTES[p.code] ?? ''}</p>
                                    <div className="plan-price">
                                        {formatNumber(p.price_uzs)} <small>сум</small>
                                    </div>
                                    <p className="t-caption muted">{p.price_uzs > 0 ? 'в месяц' : 'навсегда'}</p>
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
                                        Выбрать
                                    </Link>
                                </div>
                            );
                        })}
                    </div>
                    <p className="center mt-24 t-sm muted">
                        Оплата картой Uzcard, Humo, Visa и Mastercard. Отменить подписку можно в кабинете в один клик.
                    </p>
                </div>
            </section>
        </PublicLayout>
    );
}
