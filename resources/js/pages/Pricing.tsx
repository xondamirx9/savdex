import { Link } from '@/components/ui/Link';
import { Check, X } from 'lucide-react';
import { PublicLayout } from '@/layouts/PublicLayout';
import { routes } from '@/routes';

interface Plan {
    name: string;
    note: string;
    price: string;
    period: string;
    highlighted?: boolean;
    features: [string, boolean][];
}

/**
 * Тарифы. Цены заданы в коде временно: по §11.3 ТЗ они хранятся
 * в plan_prices по каждой валюте и правятся в админке без деплоя.
 */
const PLANS: Plan[] = [
    {
        name: 'Free',
        note: 'Попробовать площадку',
        price: '0',
        period: 'навсегда',
        features: [
            ['4 активных объявления', true],
            ['3 контакта в месяц', true],
            ['Срок показа 30 дней', true],
            ['Продвижение', false],
            ['Мини-сайт компании', false],
        ],
    },
    {
        name: 'Flash',
        note: 'Небольшая компания',
        price: '159 000',
        period: 'в месяц',
        features: [
            ['15 активных объявлений', true],
            ['15 контактов в месяц', true],
            ['15 продвижений в месяц', true],
            ['Срок показа 30 дней', true],
            ['Мини-сайт компании', false],
        ],
    },
    {
        name: 'Business',
        note: 'Оптовик и производитель',
        price: '489 000',
        period: 'в месяц',
        highlighted: true,
        features: [
            ['50 активных объявлений', true],
            ['50 контактов в месяц', true],
            ['50 продвижений в месяц', true],
            ['Срок показа 90 дней', true],
            ['Мини-сайт и расширенная аналитика', true],
        ],
    },
    {
        name: 'Premium',
        note: 'Максимальная видимость',
        price: '1 210 000',
        period: 'в месяц',
        features: [
            ['125 активных объявлений', true],
            ['125 контактов в месяц', true],
            ['125 продвижений в месяц', true],
            ['Срок показа 180 дней', true],
            ['Приоритетная поддержка', true],
        ],
    },
];

export default function Pricing() {
    return (
        <PublicLayout
            title="Тарифы"
            description="Размещение объявлений бесплатно. Тарифы Free, Flash, Business и Premium. Оплата Uzcard, Humo, Visa и Mastercard."
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
                    <div className="grid grid-4">
                        {PLANS.map((p) => (
                            <div key={p.name} className={p.highlighted ? 'plan is-hi' : 'plan'}>
                                {p.highlighted && <span className="plan-tag">Выбирают чаще всего</span>}
                                <h2 className="t-h3">{p.name}</h2>
                                <p className="t-sm muted">{p.note}</p>
                                <div className="plan-price">
                                    {p.price} <small>сум</small>
                                </div>
                                <p className="t-caption muted">{p.period}</p>
                                <ul>
                                    {p.features.map(([label, on]) => (
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
                                    className={`btn btn-block ${p.highlighted ? 'btn-primary' : 'btn-secondary'}`}
                                >
                                    Выбрать
                                </Link>
                            </div>
                        ))}
                    </div>
                    <p className="center mt-24 t-sm muted">
                        Оплата картой Uzcard, Humo, Visa и Mastercard. Отменить подписку можно в кабинете в один клик.
                    </p>
                </div>
            </section>
        </PublicLayout>
    );
}
