import { CheckCircle2, Handshake, Mail, Phone, Send, Shield, Star, Wallet } from 'lucide-react';
import { OfficeMap, type Office } from '@/components/OfficeMap';
import { PublicLayout } from '@/layouts/PublicLayout';
import { useSupport } from '@/lib/support';

/**
 * Страница «О компании» — шесть разделов, каждый со своим якорем.
 * Порядок разделов задаёт порядок пунктов подменю в шапке (§6.6 ТЗ).
 * Тексты переедут в page_blocks и станут редактируемыми в спринте 13.
 *
 * Раздел «Офис» показывается, только когда адрес заполнен в настройках
 * площадки, — поэтому оглавление собирается по факту, а не константой.
 */
const SECTIONS = [
    { id: 'about', label: 'О нас' },
    { id: 'contacts', label: 'Контакты' },
    { id: 'office', label: 'Офис на карте' },
    { id: 'help', label: 'Помощь' },
    { id: 'guide', label: 'Инструкция использования' },
    { id: 'rules', label: 'Правила размещения' },
];

const FAQ: [string, string][] = [
    [
        'Сколько стоит разместить объявление?',
        'Размещение бесплатно на всех тарифах. Бесплатный тариф даёт 4 активных объявления и 3 раскрытия контактов в месяц.',
    ],
    [
        'Почему контакты платные?',
        'Мы не берём процент со сделок, поэтому доступ к контактам — единственный источник дохода площадки. Открыв контакт компании один раз, вы видите его навсегда по всем её объявлениям.',
    ],
    [
        'Что делать, если контакт нерабочий?',
        'Нажмите «Пожаловаться на контакт» в разделе «Мои контакты». Проверим за 2 рабочих дня; при подтверждении вернём кредит и снизим компании индекс отзывчивости.',
    ],
    [
        'Как получить бейдж «Проверена»?',
        'Загрузите свидетельство о регистрации и подтвердите ИНН. Модератор проверит: на Free и Flash — до 5 рабочих дней, на Business и Premium — 1 рабочий день. Бейдж не продаётся.',
    ],
    [
        'Какими картами можно оплатить?',
        'Картами Uzcard, Humo, Visa и Mastercard через интернет-эквайринг Uzum Bank, в сумах. Платёж подтверждается кодом 3-D Secure. Подробнее — на странице «Способы оплаты».',
    ],
];

const PRINCIPLES: [typeof Shield, string, string][] = [
    [Handshake, 'Комиссию со сделок не берём', 'Сколько бы вы ни продали найденному здесь партнёру — процент мы не получаем.'],
    [Wallet, 'В расчётах не участвуем', 'Деньги между компаниями через сайт не проходят. Оплата — по вашему договору.'],
    [Shield, 'Проверяем компании вручную', 'Бейдж «Проверена» ставит модератор после сверки документов. Купить его нельзя.'],
    [Star, 'Отзывы нельзя накрутить', 'Оставить отзыв может только тот, кто оплатил раскрытие контактов компании.'],
];

const MUST: string[] = [
    'Достоверные название, ИНН и адрес компании',
    'Объявление в подходящей категории',
    'Реальные условия поставки, оплаты и объёмов',
    'Снятие объявления, когда товар закончился',
];

export default function About({
    stats,
    office,
}: {
    stats: { companies: number; categories: number; countries: number };
    office: Office | null;
}) {
    const sections = office !== null ? SECTIONS : SECTIONS.filter((s) => s.id !== 'office');
    const support = useSupport();

    return (
        <PublicLayout
            title="О компании"
            description="SAVDEX — B2B-площадка для поставщиков и закупщиков Узбекистана и Центральной Азии. Контакты, помощь, инструкция и правила размещения."
        >
            <div className="container" style={{ padding: '32px 0 96px' }}>
                <div className="grid-docs">
                    {/* Оглавление первое в разметке. На узких экранах колонка
                        схлопывается, и оно превращается в горизонтальную ленту
                        над текстом — полдюжины пунктов столбиком отодвинули бы
                        содержимое за пределы экрана. */}
                    <aside>
                        <nav className="doc-nav card" style={{ padding: 10 }} aria-label="Разделы страницы">
                            {sections.map((s) => (
                                <a key={s.id} href={`#${s.id}`}>
                                    {s.label}
                                </a>
                            ))}
                        </nav>
                    </aside>

                    <div>
                        <section id="about" className="doc-section">
                            <h1 className="t-h1" style={{ marginBottom: 12 }}>
                                О компании
                            </h1>
                            <p className="t-lead" style={{ marginBottom: 28 }}>
                                SAVDEX — площадка, на которой поставщики и закупщики находят друг друга напрямую.
                            </p>
                            <p className="t-body">
                                Мы работаем в Узбекистане и Центральной Азии. Компании публикуют, что могут поставить
                                или что хотят купить, находят партнёра и договариваются между собой. Площадка не
                                участвует в переговорах, не берёт процент со сделки и не проводит через себя деньги.
                            </p>
                            <p className="t-body mt-16">
                                Зарабатываем мы на подписке и доступе к контактам. Наш доход не зависит от суммы
                                вашего контракта.
                            </p>

                            <div className="grid grid-4 grid-tight mt-32">
                                <div className="card center">
                                    <div className="t-num">{stats.companies}</div>
                                    <div className="t-sm muted">компаний</div>
                                </div>
                                <div className="card center">
                                    <div className="t-num">0</div>
                                    <div className="t-sm muted">объявлений</div>
                                </div>
                                <div className="card center">
                                    <div className="t-num">{stats.categories}</div>
                                    <div className="t-sm muted">категорий</div>
                                </div>
                                <div className="card center">
                                    <div className="t-num">{stats.countries}</div>
                                    <div className="t-sm muted">стран</div>
                                </div>
                            </div>

                            <h2 className="t-h3 mt-48" style={{ marginBottom: 20 }}>
                                Наши принципы
                            </h2>
                            <div className="grid grid-2">
                                {PRINCIPLES.map(([Icon, title, text]) => (
                                    <div key={title} className="feature">
                                        <span className="feature-icon">
                                            <Icon aria-hidden className="size-5" />
                                        </span>
                                        <div>
                                            <h4 className="t-h4">{title}</h4>
                                            <p>{text}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </section>

                        <section id="contacts" className="doc-section">
                            <h2 className="t-h2" style={{ marginBottom: 20 }}>
                                Контакты
                            </h2>
                            <div className="grid grid-2">
                                <div className="card">
                                    <h3 className="t-h4" style={{ marginBottom: 16 }}>
                                        Оператор площадки
                                    </h3>
                                    <dl className="stack-12 t-sm">
                                        <div className="row-between">
                                            <dt className="muted">Наименование</dt>
                                            <dd>{support.legal_name}</dd>
                                        </div>
                                        <div className="row-between">
                                            <dt className="muted">ИНН</dt>
                                            <dd>{support.legal_tin}</dd>
                                        </div>
                                        <div className="row-between">
                                            <dt className="muted">Страна</dt>
                                            <dd>Узбекистан</dd>
                                        </div>
                                    </dl>
                                </div>
                                <div className="card">
                                    <h3 className="t-h4" style={{ marginBottom: 16 }}>
                                        Как с нами связаться
                                    </h3>
                                    <div className="stack-12">
                                        <a href={support.telHref} className="row" style={{ gap: 12 }}>
                                            <span className="ico-box ico-box-sm">
                                                <Phone aria-hidden className="size-4" />
                                            </span>
                                            <span>
                                                <b>{support.phone}</b>
                                                <br />
                                                <span className="t-caption muted">{support.hours}</span>
                                            </span>
                                        </a>
                                        <a href={`mailto:${support.email}`} className="row" style={{ gap: 12 }}>
                                            <span className="ico-box ico-box-sm">
                                                <Mail aria-hidden className="size-4" />
                                            </span>
                                            <span>
                                                <b>{support.email}</b>
                                                <br />
                                                <span className="t-caption muted">Поддержка, ответ за 4 часа</span>
                                            </span>
                                        </a>
                                        <a href={support.telegram} className="row" style={{ gap: 12 }}>
                                            <span className="ico-box ico-box-sm">
                                                <Send aria-hidden className="size-4" />
                                            </span>
                                            <span>
                                                <b>{support.tgHandle}</b>
                                                <br />
                                                <span className="t-caption muted">Телеграм, круглосуточно</span>
                                            </span>
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </section>

                        {office !== null && (
                            <section id="office" className="doc-section">
                                <h2 className="t-h2" style={{ marginBottom: 12 }}>
                                    Офис на карте
                                </h2>
                                <p className="t-body" style={{ marginBottom: 24 }}>
                                    Приезжайте, если вопрос проще решить лично. Договоры и документы принимаем и
                                    по почте — приезжать ради подписи необязательно.
                                </p>
                                <OfficeMap office={office} />
                            </section>
                        )}

                        <section id="help" className="doc-section">
                            <h2 className="t-h2" style={{ marginBottom: 20 }}>
                                Помощь
                            </h2>
                            {/* Нативный <details> вместо своего аккордеона: он доступен
                                с клавиатуры и работает без JavaScript */}
                            {FAQ.map(([q, a]) => (
                                <details key={q} className="accordion-item">
                                    <summary className="accordion-btn" style={{ cursor: 'pointer' }}>
                                        {q}
                                    </summary>
                                    <div className="accordion-panel">{a}</div>
                                </details>
                            ))}
                        </section>

                        <section id="guide" className="doc-section">
                            <h2 className="t-h2" style={{ marginBottom: 20 }}>
                                Инструкция использования
                            </h2>

                            <h3 className="t-h4" style={{ marginBottom: 16 }}>
                                Если вы поставщик
                            </h3>
                            <ol className="stack-16">
                                <li>
                                    <b>Зарегистрируйтесь и подтвердите почту.</b>
                                    <p className="t-sm muted mt-8">До подтверждения кабинет доступен, но публиковать нельзя.</p>
                                </li>
                                <li>
                                    <b>Заполните карточку компании.</b>
                                    <p className="t-sm muted mt-8">Заполненный профиль получает втрое больше обращений.</p>
                                </li>
                                <li>
                                    <b>Разместите объявление.</b>
                                    <p className="t-sm muted mt-8">
                                        Укажите точную марку и объём — по ним ищут. Объявления с ценой смотрят в 2,4 раза чаще.
                                    </p>
                                </li>
                                <li>
                                    <b>Следите за входящими.</b>
                                    <p className="t-sm muted mt-8">Видно, какая компания открыла ваши контакты и по какому объявлению.</p>
                                </li>
                            </ol>

                            <h3 className="t-h4 mt-32" style={{ marginBottom: 16 }}>
                                Если вы закупщик
                            </h3>
                            <ol className="stack-16">
                                <li>
                                    <b>Найдите в каталоге или опубликуйте запрос.</b>
                                    <p className="t-sm muted mt-8">Каталог виден целиком без оплаты.</p>
                                </li>
                                <li>
                                    <b>Изучите компанию до звонка.</b>
                                    <p className="t-sm muted mt-8">Документы, рейтинг, отзывы, срок на площадке — всё открыто.</p>
                                </li>
                                <li>
                                    <b>Откройте контакт.</b>
                                    <p className="t-sm muted mt-8">Кредит списывается за компанию, а не за объявление.</p>
                                </li>
                            </ol>
                        </section>

                        <section id="rules" className="doc-section">
                            <h2 className="t-h2" style={{ marginBottom: 20 }}>
                                Правила размещения
                            </h2>
                            <div className="alert alert-danger" style={{ marginBottom: 24 }}>
                                <Shield aria-hidden className="size-5" />
                                <div>
                                    <b>Контактные данные в тексте объявления запрещены.</b> Телефон, почта, ссылки и
                                    ники в мессенджерах автоматически скрываются. Контакты передаются только через
                                    раскрытие контактов — на этом работает площадка.
                                </div>
                            </div>
                            <h3 className="t-h4" style={{ marginBottom: 16 }}>
                                Что обязательно
                            </h3>
                            <ul className="stack-12">
                                {MUST.map((t) => (
                                    <li key={t} className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
                                        <CheckCircle2 aria-hidden className="text-success mt-0.5 size-5 shrink-0" />
                                        <span>{t}</span>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    </div>
                </div>
            </div>
        </PublicLayout>
    );
}
