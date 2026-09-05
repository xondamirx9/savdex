import { Link } from '@/components/ui/Link';
import { ArrowLeft, Building2, CalendarDays, ExternalLink, Mail, MapPin, Phone, User, Wallet } from 'lucide-react';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';
import { budgetLabel, deadlineBadge, TenderCard, type TenderRow } from './Index';

interface Tender extends TenderRow {
    description: string[];
    source_url: string | null;
    contact_name: string | null;
    contact_phone: string | null;
    contact_email: string | null;
    parent_category: string | null;
}

export default function TenderShow({ tender, similar }: { tender: Tender; similar: TenderRow[] }) {
    const place = [tender.location, tender.country].filter(Boolean).join(', ');
    const hasContacts = tender.contact_name || tender.contact_phone || tender.contact_email;

    return (
        <PublicLayout title={tender.title} description={tender.excerpt}>
            <div className="container" style={{ padding: '24px 0 96px' }}>
                <nav aria-label={t('tenders.breadcrumbs')} style={{ paddingBottom: 20 }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>{t('tenders.home')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li>
                            <Link href={routes.tenders}>{t('tenders.h1')}</Link>
                        </li>
                        {tender.category && (
                            <>
                                <li aria-hidden="true">/</li>
                                <li aria-current="page" style={{ color: 'var(--text)' }}>
                                    {tender.category}
                                </li>
                            </>
                        )}
                    </ol>
                </nav>

                <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) 340px', gap: 32, alignItems: 'start' }}>
                    <article style={{ maxWidth: '72ch' }}>
                        <div className="row wrap" style={{ gap: 10, marginBottom: 16 }}>
                            {deadlineBadge(tender)}
                            {tender.category && <span className="badge badge-neutral">{tender.category}</span>}
                            {tender.published && (
                                <span className="t-caption muted row" style={{ gap: 6 }}>
                                    <CalendarDays aria-hidden className="size-3.5" /> {t('tenders.published')}: {tender.published}
                                </span>
                            )}
                        </div>

                        <h1 className="t-h1">{tender.title}</h1>

                        <div className="mt-32">
                            {tender.description.length > 0 && tender.description[0] !== '' ? (
                                tender.description.map((p, i) => (
                                    <p key={i} className="t-body" style={{ marginBottom: 18 }}>
                                        {p}
                                    </p>
                                ))
                            ) : (
                                <p className="t-body muted">{t('tenders.no_description')}</p>
                            )}
                        </div>

                        {tender.source_url && (
                            <a
                                href={tender.source_url}
                                target="_blank"
                                rel="noopener noreferrer nofollow"
                                className="btn btn-primary mt-24"
                            >
                                {t('tenders.open_source')} <ExternalLink aria-hidden className="size-4" />
                            </a>
                        )}

                        <div className="mt-48" style={{ paddingTop: 24, borderTop: '1px solid var(--border)' }}>
                            <Link href={routes.tenders} className="btn btn-secondary">
                                <ArrowLeft aria-hidden className="size-4" /> {t('tenders.back')}
                            </Link>
                        </div>
                    </article>

                    <aside className="card" style={{ display: 'grid', gap: 16 }}>
                        <div>
                            <div className="t-caption muted">{t('tenders.budget')}</div>
                            <div className="t-h3 row" style={{ gap: 8 }}>
                                <Wallet aria-hidden className="size-5 muted" /> {budgetLabel(tender.budget, tender.currency)}
                            </div>
                        </div>

                        <div>
                            <div className="t-caption muted">{t('tenders.deadline')}</div>
                            <div className="t-body row" style={{ gap: 8 }}>
                                <CalendarDays aria-hidden className="size-4 muted" />
                                {tender.deadline ?? t('tenders.deadline_none')}
                            </div>
                        </div>

                        {tender.customer && (
                            <div>
                                <div className="t-caption muted">{t('tenders.customer')}</div>
                                <div className="t-body row" style={{ gap: 8 }}>
                                    <Building2 aria-hidden className="size-4 muted" /> {tender.customer}
                                </div>
                            </div>
                        )}

                        {place && (
                            <div>
                                <div className="t-caption muted">{t('tenders.location')}</div>
                                <div className="t-body row" style={{ gap: 8 }}>
                                    <MapPin aria-hidden className="size-4 muted" /> {place}
                                </div>
                            </div>
                        )}

                        {hasContacts && (
                            <div style={{ paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                                <div className="t-caption muted" style={{ marginBottom: 8 }}>
                                    {t('tenders.contacts')}
                                </div>
                                <div style={{ display: 'grid', gap: 8 }}>
                                    {tender.contact_name && (
                                        <div className="t-sm row" style={{ gap: 8 }}>
                                            <User aria-hidden className="size-4 muted" /> {tender.contact_name}
                                        </div>
                                    )}
                                    {tender.contact_phone && (
                                        <a href={`tel:${tender.contact_phone.replace(/[^\d+]/g, '')}`} className="t-sm row" style={{ gap: 8 }}>
                                            <Phone aria-hidden className="size-4 muted" /> {tender.contact_phone}
                                        </a>
                                    )}
                                    {tender.contact_email && (
                                        <a href={`mailto:${tender.contact_email}`} className="t-sm row" style={{ gap: 8 }}>
                                            <Mail aria-hidden className="size-4 muted" /> {tender.contact_email}
                                        </a>
                                    )}
                                </div>
                            </div>
                        )}
                    </aside>
                </div>

                {similar.length > 0 && (
                    <section className="mt-48">
                        <h2 className="t-h3" style={{ marginBottom: 20 }}>
                            {t('tenders.similar')}
                        </h2>
                        <div className="grid grid-3">
                            {similar.map((row) => (
                                <TenderCard key={row.id} row={row} />
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </PublicLayout>
    );
}
