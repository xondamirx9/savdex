import { router } from '@inertiajs/react';
import { Handshake, Mail, Phone, Send, Shield, Star, Wallet } from 'lucide-react';
import { useEffect, useState } from 'react';
import { DocsNav, type DocsNavItem } from '@/components/docs/DocsNav';
import { PageBlocks, type PageCard } from '@/components/docs/PageBlocks';
import { OfficeMap, type Office } from '@/components/OfficeMap';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t } from '@/lib/i18n';
import { useSupport } from '@/lib/support';

/**
 * Страница «О компании» — о площадке, контакты и офис, каждый раздел
 * со своим якорем.
 *
 * Тексты — из админки («Страницы и FAQ»), на языке посетителя: «О нас»
 * — страница about, текст под «Контактами» и текст раздела офиса —
 * страница contacts. Принципы и счётчики — часть вёрстки, их подписи
 * в словаре.
 *
 * «Помощь», «Инструкция» и «Правила» переехали на свои адреса
 * (DocPage); старые ссылки с якорем /about#help ведут туда.
 *
 * Раздел «Офис» показывается, только когда адрес заполнен в настройках
 * площадки, — поэтому оглавление собирает сервер.
 */
const MOVED = ['help', 'guide', 'rules'];

/** Иконка остаётся в коде, текст — в словаре. */
const PRINCIPLES: [typeof Shield, string][] = [
    [Handshake, 'commission'],
    [Wallet, 'money'],
    [Shield, 'check'],
    [Star, 'reviews'],
];

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
    page,
    contacts,
    nav,
}: {
    stats: { companies: number; listings: number; categories: number; countries: number };
    office: Office | null;
    page: PageCard | null;
    contacts: PageCard | null;
    nav: DocsNavItem[];
}) {
    const sections = ['about', 'contacts', ...(office !== null ? ['office'] : [])];
    const support = useSupport();
    const active = useActiveSection(sections);

    // Старые ссылки на разделы, переехавшие на свои адреса. Якорь до
    // сервера не доходит — перевести может только сама страница
    useEffect(() => {
        const hash = window.location.hash.slice(1);

        if (MOVED.includes(hash)) router.visit(`/${hash}`, { replace: true });
    }, []);

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
                    <DocsNav items={nav} active={active} onAbout />

                    <div>
                        <section id="about" className="doc-section">
                            <h1 className="t-h1" style={{ marginBottom: 8 }}>
                                {page?.title ?? t('about.title')}
                            </h1>
                            {page && page.lead !== '' && (
                                <p className="t-lead" style={{ marginBottom: 16 }}>
                                    {page.lead}
                                </p>
                            )}
                            {page && <PageBlocks blocks={page.blocks} />}

                            <div className="grid grid-4 grid-tight mt-24">
                                <div className="card center">
                                    <div className="t-num">{stats.companies}</div>
                                    <div className="t-sm muted">{t('about.stats.companies')}</div>
                                </div>
                                <div className="card center">
                                    <div className="t-num">{stats.listings}</div>
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
                                {contacts?.title ?? t('about.nav.contacts')}
                            </h2>
                            {contacts && contacts.lead !== '' && (
                                <p className="t-body" style={{ marginBottom: 16 }}>
                                    {contacts.lead}
                                </p>
                            )}
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
                                                <span className="t-caption muted">{t('contacts.hours_value')}</span>
                                            </span>
                                        </a>
                                        <a href={`mailto:${support.email}`} className="row contact-link" style={{ gap: 12 }}>
                                            <span className="ico-box ico-box-sm">
                                                <Mail aria-hidden className="size-4" />
                                            </span>
                                            <span>
                                                <b>{support.email}</b>
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
                                {contacts && contacts.blocks.length > 0 && (
                                    <div style={{ marginBottom: 24 }}>
                                        <PageBlocks blocks={contacts.blocks} />
                                    </div>
                                )}
                                <OfficeMap office={office} />
                            </section>
                        )}

                    </div>
                </div>
            </div>
        </PublicLayout>
    );
}
