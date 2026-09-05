import { Handshake, Headphones, ShieldCheck, TrendingUp } from 'lucide-react';
import { PaymentBadges } from '@/components/PaymentLogos';
import { Link } from '@/components/ui/Link';
import { Logo } from '@/components/ui';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Состав подвала — функцией, а не константой модуля: подписи берутся
 * из словаря, который приходит с сервером уже после загрузки файла.
 */
function columns() {
    return [
        {
            title: t('footer.platform'),
            links: [
                { href: routes.catalog, label: t('nav.products') },
                { href: routes.companies, label: t('nav.companies') },
                { href: `${routes.catalog}?type=demand`, label: t('nav.rfq') },
                { href: routes.tenders, label: t('nav.tenders') },
                { href: routes.countries, label: t('nav.countries') },
                { href: routes.pricing, label: t('nav.pricing') },
            ],
        },
        {
            title: t('nav.about'),
            links: [
                { href: routes.about, label: t('nav.about_us') },
                { href: routes.contacts, label: t('nav.contacts') },
                { href: routes.news, label: t('nav.news') },
                { href: `${routes.about}#help`, label: t('nav.help') },
                { href: `${routes.about}#guide`, label: t('footer.guide') },
            ],
        },
        {
            title: t('footer.documents'),
            links: [
                { href: `${routes.about}#rules`, label: t('nav.rules') },
                { href: routes.terms, label: t('footer.terms') },
                { href: routes.payment, label: t('footer.payment') },
                { href: routes.security, label: t('footer.security') },
                { href: routes.privacy, label: t('footer.privacy') },
                { href: routes.refunds, label: t('footer.refunds') },
            ],
        },
    ];
}

/** Полоса преимуществ — четыре обещания площадки над подвалом. */
function features(): [typeof ShieldCheck, string, string][] {
    return [
        [ShieldCheck, t('footer.f1_title'), t('footer.f1_text')],
        [Handshake, t('footer.f2_title'), t('footer.f2_text')],
        [Headphones, t('footer.f3_title'), t('footer.f3_text')],
        [TrendingUp, t('footer.f4_title'), t('footer.f4_text')],
    ];
}

export function SiteFooter() {
    return (
        <>
            <section className="features-band" aria-label={t('footer.features_label')}>
                <div className="container">
                    <div className="features-grid">
                        {features().map(([Icon, title, text]) => (
                            <div key={title} className="feature-b2b">
                                <span className="feature-b2b-ico">
                                    <Icon aria-hidden className="size-6" />
                                </span>
                                <div>
                                    <h3>{title}</h3>
                                    <p>{text}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            <footer className="footer">
                <div className="container">
                    <div className="footer-grid">
                        <div>
                            <Link href={routes.home} className="logo" style={{ marginBottom: 14 }} aria-label={t('nav.home_link')}>
                                <Logo asContent />
                            </Link>
                            <p className="t-sm muted prose">{t('footer.about')}</p>
                            {/* Логотипы ПС и пометка о 3-D Secure — требование банка-эквайера */}
                            <div className="mt-16">
                                <PaymentBadges />
                            </div>
                            <Link href={routes.security} className="pay-note">
                                <ShieldCheck aria-hidden className="size-4" />
                                {t('footer.secure_note')}
                            </Link>
                        </div>

                        {columns().map((col) => (
                            <div key={col.title}>
                                <h2 className="footer-title">{col.title}</h2>
                                <ul>
                                    {col.links.map((l) => (
                                        <li key={l.href + l.label}>
                                            <Link href={l.href}>{l.label}</Link>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ))}
                    </div>

                    <div className="footer-bot">
                        <span>{t('footer.copyright')}</span>
                        <span>{t('footer.no_commission')}</span>
                    </div>
                </div>
            </footer>
        </>
    );
}
