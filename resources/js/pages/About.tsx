import { CheckCircle2, Handshake, Mail, Phone, Send, Shield, Star, Wallet } from 'lucide-react';
import { useEffect, useState } from 'react';
import { OfficeMap, type Office } from '@/components/OfficeMap';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t } from '@/lib/i18n';
import { useSupport } from '@/lib/support';

/**
 * Страница «О компании» — шесть разделов, каждый со своим якорем.
 * Порядок разделов задаёт порядок пунктов подменю в шапке (§6.6 ТЗ).
 *
 * Тексты живут в словарях lang/<язык>/ui.php: страница переводится
 * вместе с остальной витриной, а не остаётся русской на узбекской.
 * Здесь только идентификаторы — подписи подставляет t() при
 * отрисовке, когда словарь уже пришёл с сервера.
 *
 * Раздел «Офис» показывается, только когда адрес заполнен в настройках
 * площадки, — поэтому оглавление собирается по факту, а не константой.
 */
const SECTION_IDS = ['about', 'contacts', 'office', 'help', 'guide', 'rules'] as const;

const FAQ_ITEMS = [1, 2, 3, 4, 5] as const;

/** Иконка остаётся в коде, текст — в словаре. */
const PRINCIPLES: [typeof Shield, string][] = [
    [Handshake, 'commission'],
    [Wallet, 'money'],
    [Shield, 'check'],
    [Star, 'reviews'],
];

const SUPPLIER_STEPS = [1, 2, 3, 4] as const;

const BUYER_STEPS = [1, 2, 3] as const;

const MUST_ITEMS = [1, 2, 3, 4] as const;

/**
 * Раздел, который сейчас на экране, — для подсветки пункта оглавления.
 *
 * Наблюдатель, а не обработчик прокрутки: пересчёт границ на каждый
 * пиксель прокрутки заметен на длинной странице, а здесь браузер
 * будит нас только на пересечении.
 */
function useActiveSection(ids: string[]): string {
    const key = ids.join(',');
    const [active, setActive] = useState(ids[0] ?? '');

    useEffect(() => {
        const targets = ids
            .map((id) => document.getElementById(id))
            .filter((el): el is HTMLElement => el !== null);

        if (targets.length === 0) return;

        const io = new IntersectionObserver(
            (entries) => {
                // Верхний из видимых: при прокрутке на экране обычно
                // два соседних раздела, и подсвечивать нужно первый
                const top = entries
                    .filter((e) => e.isIntersecting)
                    .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];

                if (top) setActive(top.target.id);
            },
            // Верхняя граница — под шапкой, нижняя отрезает хвост экрана:
            // иначе активным становился раздел, едва показавшийся снизу
            { rootMargin: '-96px 0px -60% 0px', threshold: 0 },
        );

        targets.forEach((el) => io.observe(el));

        return () => io.disconnect();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]);

    return active;
}

export default function About({
    stats,
    office,
}: {
    stats: { companies: number; categories: number; countries: number };
    office: Office | null;
}) {
    const sections = office !== null ? [...SECTION_IDS] : SECTION_IDS.filter((id) => id !== 'office');
    const support = useSupport();
    const active = useActiveSection(sections);

    return (
        <PublicLayout
            title={t('about.title')}
            description={t('about.description')}
        >
            <div className="container about-page">
                <div className="grid-docs">
                    {/* Оглавление первое в разметке. На узких экранах колонка
                        схлопывается, и оно превращается в горизонтальную ленту
                        над текстом — полдюжины пунктов столбиком отодвинули бы
                        содержимое за пределы экрана. */}
                    <aside>
                        <nav className="doc-nav card" style={{ padding: 10 }} aria-label={t('about.sections')}>
                            {sections.map((id) => (
                                <a key={id} href={`#${id}`} aria-current={active === id ? 'true' : undefined}>
                                    {t(`about.nav.${id}`)}
                                </a>
                            ))}
                        </nav>
                    </aside>

                    <div>
                        <section id="about" className="doc-section">
                            <h1 className="t-h1" style={{ marginBottom: 8 }}>
                                {t('about.title')}
                            </h1>
                            <p className="t-lead" style={{ marginBottom: 16 }}>
                                {t('about.lead')}
                            </p>
                            <p className="t-body">{t('about.text_1')}</p>
                            <p className="t-body mt-16">{t('about.text_2')}</p>

                            <div className="grid grid-4 grid-tight mt-24">
                                <div className="card center">
                                    <div className="t-num">{stats.companies}</div>
                                    <div className="t-sm muted">{t('about.stats.companies')}</div>
                                </div>
                                <div className="card center">
                                    <div className="t-num">0</div>
                                    <div className="t-sm muted">{t('about.stats.listings')}</div>
                                </div>
                                <div className="card center">
                                    <div className="t-num">{stats.categories}</div>
                                    <div className="t-sm muted">{t('about.stats.categories')}</div>
                                </div>
                                <div className="card center">
                                    <div className="t-num">{stats.countries}</div>
                                    <div className="t-sm muted">{t('about.stats.countries')}</div>
                                </div>
                            </div>

                            <h2 className="t-h3 mt-32" style={{ marginBottom: 12 }}>
                                {t('about.principles_title')}
                            </h2>
                            <div className="grid grid-2">
                                {PRINCIPLES.map(([Icon, key]) => (
                                    <div key={key} className="feature">
                                        <span className="feature-icon">
                                            <Icon aria-hidden className="size-5" />
                                        </span>
                                        <div>
                                            <h4 className="t-h4">{t(`about.principles.${key}_title`)}</h4>
                                            <p>{t(`about.principles.${key}_text`)}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </section>

                        <section id="contacts" className="doc-section contacts-section">
                            <h2 className="t-h2" style={{ marginBottom: 12 }}>
                                {t('about.nav.contacts')}
                            </h2>
                            <div className="grid grid-2 contacts-cards" data-reveal-stagger>
                                <div className="card">
                                    <h3 className="t-h4" style={{ marginBottom: 16 }}>
                                        {t('about.operator')}
                                    </h3>
                                    <dl className="stack-12 t-sm">
                                        <div className="row-between">
                                            <dt className="muted">{t('about.legal_name')}</dt>
                                            <dd>{support.legal_name}</dd>
                                        </div>
                                        <div className="row-between">
                                            <dt className="muted">{t('about.tin')}</dt>
                                            <dd>{support.legal_tin}</dd>
                                        </div>
                                        <div className="row-between">
                                            <dt className="muted">{t('about.country')}</dt>
                                            <dd>{t('about.country_value')}</dd>
                                        </div>
                                    </dl>
                                </div>
                                <div className="card">
                                    <h3 className="t-h4" style={{ marginBottom: 16 }}>
                                        {t('about.reach_us')}
                                    </h3>
                                    <div className="stack-12">
                                        <a href={support.telHref} className="row contact-link" style={{ gap: 12 }}>
                                            <span className="ico-box ico-box-sm">
                                                <Phone aria-hidden className="size-4" />
                                            </span>
                                            <span>
                                                <b>{support.phone}</b>
                                                <br />
                                                <span className="t-caption muted">{support.hours}</span>
                                            </span>
                                        </a>
                                        <a href={`mailto:${support.email}`} className="row contact-link" style={{ gap: 12 }}>
                                            <span className="ico-box ico-box-sm">
                                                <Mail aria-hidden className="size-4" />
                                            </span>
                                            <span>
                                                <b>{support.email}</b>
                                                <br />
                                                <span className="t-caption muted">{t('about.support_hint')}</span>
                                            </span>
                                        </a>
                                        <a href={support.telegram} className="row contact-link" style={{ gap: 12 }}>
                                            <span className="ico-box ico-box-sm">
                                                <Send aria-hidden className="size-4" />
                                            </span>
                                            <span>
                                                <b>{support.tgHandle}</b>
                                                <br />
                                                <span className="t-caption muted">{t('about.telegram_hint')}</span>
                                            </span>
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </section>

                        {office !== null && (
                            <section id="office" className="doc-section">
                                <h2 className="t-h2" style={{ marginBottom: 10 }}>
                                    {t('about.nav.office')}
                                </h2>
                                <p className="t-body" style={{ marginBottom: 24 }}>
                                    {t('about.office_text')}
                                </p>
                                <OfficeMap office={office} />
                            </section>
                        )}

                        <section id="help" className="doc-section">
                            <h2 className="t-h2" style={{ marginBottom: 12 }}>
                                {t('about.nav.help')}
                            </h2>
                            {/* Нативный <details> вместо своего аккордеона: он доступен
                                с клавиатуры и работает без JavaScript */}
                            {FAQ_ITEMS.map((n) => (
                                <details key={n} className="accordion-item">
                                    <summary className="accordion-btn" style={{ cursor: 'pointer' }}>
                                        {t(`about.faq.q${n}`)}
                                    </summary>
                                    <div className="accordion-panel">{t(`about.faq.a${n}`)}</div>
                                </details>
                            ))}
                        </section>

                        <section id="guide" className="doc-section">
                            <h2 className="t-h2" style={{ marginBottom: 12 }}>
                                {t('about.nav.guide')}
                            </h2>

                            <h3 className="t-h4" style={{ marginBottom: 16 }}>
                                {t('about.supplier_title')}
                            </h3>
                            <ol className="stack-16">
                                {SUPPLIER_STEPS.map((n) => (
                                    <li key={n}>
                                        <b>{t(`about.supplier.step_${n}`)}</b>
                                        <p className="t-sm muted mt-8">{t(`about.supplier.hint_${n}`)}</p>
                                    </li>
                                ))}
                            </ol>

                            <h3 className="t-h4 mt-32" style={{ marginBottom: 16 }}>
                                {t('about.buyer_title')}
                            </h3>
                            <ol className="stack-16">
                                {BUYER_STEPS.map((n) => (
                                    <li key={n}>
                                        <b>{t(`about.buyer.step_${n}`)}</b>
                                        <p className="t-sm muted mt-8">{t(`about.buyer.hint_${n}`)}</p>
                                    </li>
                                ))}
                            </ol>
                        </section>

                        <section id="rules" className="doc-section">
                            <h2 className="t-h2" style={{ marginBottom: 12 }}>
                                {t('about.nav.rules')}
                            </h2>
                            <div className="alert alert-danger" style={{ marginBottom: 24 }}>
                                <Shield aria-hidden className="size-5" />
                                <div>
                                    <b>{t('about.rules_warning_title')}</b> {t('about.rules_warning_text')}
                                </div>
                            </div>
                            <h3 className="t-h4" style={{ marginBottom: 16 }}>
                                {t('about.must_title')}
                            </h3>
                            <ul className="stack-12">
                                {MUST_ITEMS.map((n) => (
                                    <li key={n} className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
                                        <CheckCircle2 aria-hidden className="text-success mt-0.5 size-5 shrink-0" />
                                        <span>{t(`about.must.item_${n}`)}</span>
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
