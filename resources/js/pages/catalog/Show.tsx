import { useForm, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import {
    BadgeCheck,
    Eye,
    Globe,
    Lock,
    Mail,
    MessageSquareText,
    Package,
    Phone,
    Send,
    ShoppingCart,
    Truck,
    Wallet,
} from 'lucide-react';
import { useState } from 'react';
import { Modal } from '@/components/Modal';
import { formatNumber } from '@/components/cabinet';
import { Gallery } from '@/components/Gallery';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

interface Contact {
    type: string;
    value: string;
    href: string | null;
    locked: boolean;
}

interface Listing {
    id: number;
    title: string;
    description: string | null;
    type: 'supply' | 'demand';
    category: string | null;
    price: number | null;
    currency: string;
    unit: string | null;
    negotiable: boolean;
    min_order: number | null;
    delivery_terms: string | null;
    payment_terms: string | null;
    city: string | null;
    published: string | null;
    expires: string | null;
    views: number;
    attributes: { key: string; value: string }[];
    images: { id: number; url: string; thumb: string }[];
    badges: string[];
    promoted: boolean;
    tags: string[];
}

interface Similar {
    id: number;
    slug: string | null;
    title: string;
    price: number | null;
    currency: string;
    unit: string | null;
    negotiable: boolean;
    company: { name: string | null };
}

const CONTACT_ICONS: Record<string, typeof Phone> = {
    phone: Phone,
    email: Mail,
    telegram: Send,
    whatsapp: Send,
    website: Globe,
};

export default function ListingShow({
    listing,
    company,
    contacts,
    unlocked,
    preview,
    respond,
    similar,
}: {
    listing: Listing;
    company: {
        name: string | null;
        slug: string | null;
        initials: string | null;
        verification_level: number;
        rating: number;
        reviews_count: number;
        city: string | null;
        country: string | null;
    };
    contacts: Contact[];
    unlocked: boolean;
    preview: boolean;
    respond: { guest: boolean; owner: boolean };
    similar: Similar[];
}) {
    const { auth } = usePage<SharedProps>().props;
    const [unlockOpen, setUnlockOpen] = useState(false);
    const unlockForm = useForm({ listing_id: listing.id });

    const lockedCount = contacts.filter((c) => c.locked).length;
    const TypeIcon = listing.type === 'demand' ? ShoppingCart : Package;

    const currency = listing.currency === 'UZS' ? t('catalog.currency_uzs') : listing.currency;

    const price = listing.negotiable || listing.price === null
        ? t('catalog.price_negotiable')
        : `${formatNumber(listing.price)} ${currency}${listing.unit ? `/${listing.unit}` : ''}`;

    return (
        <PublicLayout
            title={listing.title}
            description={(listing.description ?? '').slice(0, 160)}
        >
            <div className="container" style={{ paddingBottom: 96 }}>
                {/* Предпросмотр: страницу в этом статусе видит только
                    владелец — покупатели получают 404 до публикации */}
                {preview && (
                    <div className="alert alert-info" style={{ marginTop: 20, alignItems: 'center' }}>
                        <Eye aria-hidden className="size-5 shrink-0" />
                        <div style={{ flex: 1, minWidth: 200 }}>
                            <b>{t('listing.preview_title')}</b>
                            <br />
                            <span className="t-sm">{t('listing.preview_text')}</span>
                        </div>
                        <Link href={routes.listingEdit(listing.id)} className="btn btn-secondary btn-sm shrink-0">
                            {t('listing.preview_edit')}
                        </Link>
                    </div>
                )}

                <nav aria-label={t('listing.breadcrumbs')} style={{ padding: '20px 0 16px' }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li><Link href={routes.home}>{t('listing.home')}</Link></li>
                        <li aria-hidden="true">/</li>
                        <li><Link href={routes.catalog}>{t('listing.catalog')}</Link></li>
                        {listing.category && (
                            <>
                                <li aria-hidden="true">/</li>
                                <li>{listing.category}</li>
                            </>
                        )}
                    </ol>
                </nav>

                <div className="grid grid-sidebar" style={{ ['--aside' as string]: '340px', gap: 24, alignItems: 'start' }}>
                    <div className="min-w-0">
                        <div className="card">
                            <div className="row wrap" style={{ gap: 10, marginBottom: 14 }}>
                                <span className={cn('badge', listing.type === 'demand' ? 'badge-demand' : 'badge-supply')}>
                                    <TypeIcon aria-hidden className="size-3.5" />
                                    {listing.type === 'demand' ? t('catalog.badge_demand') : t('catalog.badge_supply')}
                                </span>
                                {listing.badges.map((b) => (
                                    <span key={b} className="badge badge-top">{b}</span>
                                ))}
                                {listing.promoted && <span className="badge badge-promoted">{t('catalog.badge_promoted')}</span>}
                            </div>

                            <h1 className="t-h1">{listing.title}</h1>

                            {listing.images.length > 0 && (
                                <div className="mt-24">
                                    <Gallery images={listing.images} alt={listing.title} />
                                </div>
                            )}

                            <p className="t-num mt-16" style={{ fontSize: 28 }}>{price}</p>

                            <div className="row wrap t-caption muted mt-16" style={{ gap: 16 }}>
                                {listing.published && <span>{t('listing.published', { date: listing.published })}</span>}
                                {listing.city && <span>{listing.city}</span>}
                                <span className="row" style={{ gap: 5 }}>
                                    <Eye aria-hidden className="size-3.5" /> {listing.views}
                                </span>
                            </div>

                            {listing.description && (
                                <div className="mt-24">
                                    {listing.description.split(/\n{2,}/).map((p, i) => (
                                        <p key={i} className="t-body" style={{ marginBottom: 14 }}>{p}</p>
                                    ))}
                                </div>
                            )}

                            {listing.attributes.length > 0 && (
                                <dl className="card-facts mt-24">
                                    {listing.attributes.map((a) => (
                                        <div key={a.key} className="fact">
                                            <dt>{a.key}</dt>
                                            <dd>{a.value}</dd>
                                        </div>
                                    ))}
                                </dl>
                            )}

                            {(listing.delivery_terms || listing.payment_terms || listing.min_order) && (
                                <div className="mt-24" style={{ paddingTop: 20, borderTop: '1px solid var(--border)' }}>
                                    <h2 className="t-h4" style={{ marginBottom: 12 }}>{t('listing.terms')}</h2>

                                    {listing.min_order && (
                                        <p className="t-sm" style={{ marginBottom: 8 }}>
                                            <b>{t('listing.min_order')}</b> {formatNumber(listing.min_order)}
                                            {listing.unit ? ` ${listing.unit}` : ''}
                                        </p>
                                    )}
                                    {listing.delivery_terms && (
                                        <p className="t-sm" style={{ marginBottom: 8 }}>
                                            <Truck aria-hidden className="inline size-4" /> {listing.delivery_terms}
                                        </p>
                                    )}
                                    {listing.payment_terms && (
                                        <p className="t-sm">
                                            <Wallet aria-hidden className="inline size-4" /> {listing.payment_terms}
                                        </p>
                                    )}
                                </div>
                            )}

                            {/* Теги — автоматически из заголовка, категории
                                и характеристик; клик уводит в поиск каталога */}
                            {listing.tags.length > 0 && (
                                <div className="mt-24" style={{ paddingTop: 20, borderTop: '1px solid var(--border)' }}>
                                    <h2 className="t-h4" style={{ marginBottom: 12 }}>{t('listing.tags_title')}</h2>
                                    <div className="row wrap" style={{ gap: 8 }}>
                                        {listing.tags.map((tag) => (
                                            <Link
                                                key={tag}
                                                href={`${routes.catalog}?q=${encodeURIComponent(tag)}`}
                                                className="listing-tag"
                                            >
                                                #{tag.replace(/\s+/g, '')}
                                            </Link>
                                        ))}
                                    </div>
                                    <p className="t-caption muted mt-8">{t('listing.tags_hint')}</p>
                                </div>
                            )}
                        </div>

                        {similar.length > 0 && (
                            <section className="mt-32">
                                <h2 className="t-h3" style={{ marginBottom: 16 }}>{t('listing.similar')}</h2>
                                <div className="grid grid-2">
                                    {similar.map((s) => (
                                        <Link
                                            key={s.id}
                                            href={s.slug ? routes.listing(s.slug) : routes.catalog}
                                            className="card lift"
                                            style={{ color: 'inherit' }}
                                        >
                                            <b>{s.title}</b>
                                            <p className="t-sm muted mt-8">{s.company.name}</p>
                                            <p className="t-sm mt-8">
                                                {s.negotiable || s.price === null
                                                    ? t('catalog.price_negotiable')
                                                    : `${formatNumber(s.price)} ${s.currency === 'UZS' ? t('catalog.currency_uzs') : s.currency}`}
                                            </p>
                                        </Link>
                                    ))}
                                </div>
                            </section>
                        )}
                    </div>

                    <aside className="stack-16">
                        <RespondCard listingId={listing.id} guest={respond.guest} owner={respond.owner} />

                        <div className="card">
                            <div className="row" style={{ gap: 12, marginBottom: 16 }}>
                                <span className="listing-logo logo-48">{company.initials}</span>
                                <div style={{ minWidth: 0 }}>
                                    <b>
                                        {company.slug ? (
                                            <Link href={routes.company(company.slug)}>{company.name}</Link>
                                        ) : (
                                            company.name
                                        )}
                                    </b>
                                    <p className="t-caption muted">
                                        {[company.city, company.country].filter(Boolean).join(' · ')}
                                    </p>
                                </div>
                            </div>

                            {company.verification_level >= 2 && (
                                <p className="t-sm" style={{ color: 'var(--success)', marginBottom: 12 }}>
                                    <BadgeCheck aria-hidden className="inline size-4" /> {t('listing.company_verified')}
                                </p>
                            )}

                            {company.reviews_count > 0 && (
                                <p className="t-sm muted" style={{ marginBottom: 16 }}>
                                    {t('listing.rating', { rating: company.rating.toFixed(1) })} ·{' '}
                                    {tChoice('listing.reviews', company.reviews_count)}
                                </p>
                            )}

                            <div className="contacts-grid">
                                {contacts.map((c, i) => {
                                    const Icon = CONTACT_ICONS[c.type] ?? Phone;
                                    return (
                                        <div key={i} className={cn('contact-item', c.locked ? 'is-locked' : 'is-open')}>
                                            <span className="ico-box ico-box-sm">
                                                <Icon aria-hidden className="size-4" />
                                            </span>
                                            <div className="contact-value">
                                                {c.href ? <a href={c.href}>{c.value}</a> : c.value}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {lockedCount > 0 && (
                                <>
                                    {auth?.user ? (
                                        <button className="btn btn-primary btn-block mt-16" onClick={() => setUnlockOpen(true)}>
                                            <Lock aria-hidden className="size-4" /> {t('listing.show_contacts')}
                                        </button>
                                    ) : (
                                        <Link href={routes.register} className="btn btn-primary btn-block mt-16">
                                            <Lock aria-hidden className="size-4" /> {t('listing.show_contacts')}
                                        </Link>
                                    )}

                                    <p className="t-caption muted mt-8">
                                        {t('listing.contacts_hint')}
                                    </p>
                                </>
                            )}

                            {unlocked && (
                                <p className="t-caption mt-16" style={{ color: 'var(--success)' }}>
                                    {t('listing.already_open')}
                                </p>
                            )}
                        </div>

                        <div className="card" style={{ background: 'var(--primary-50)', borderColor: 'var(--primary-100)' }}>
                            <p className="t-sm">
                                <b>{t('listing.no_commission_bold')}</b> {t('listing.no_commission_text')}
                            </p>
                        </div>
                    </aside>
                </div>
            </div>

            <Modal
                open={unlockOpen}
                onClose={() => setUnlockOpen(false)}
                title={t('listing.unlock_title')}
                description={company.name ?? undefined}
                width={460}
                footer={
                    <>
                        <button
                            className="btn btn-primary"
                            style={{ flex: 1 }}
                            disabled={unlockForm.processing}
                            onClick={() =>
                                unlockForm.post(`/company/${company.slug}/unlock`, {
                                    preserveScroll: true,
                                    onSuccess: () => setUnlockOpen(false),
                                })
                            }
                        >
                            {unlockForm.processing ? t('listing.unlock_processing') : t('listing.unlock_action')}
                        </button>
                        <button className="btn btn-ghost" onClick={() => setUnlockOpen(false)}>
                            {t('listing.cancel')}
                        </button>
                    </>
                }
            >
                <p className="t-sm">
                    {t('listing.unlock_text_before')} <b>{t('listing.unlock_text_bold')}</b>{' '}
                    {t('listing.unlock_text_after')}
                </p>
            </Modal>
        </PublicLayout>
    );
}


/**
 * Отклик на объявление — начало разговора в чате площадки.
 *
 * Владельцу не показывается: сервер такой отклик всё равно отклонит.
 * Гостя кнопка ведёт на вход — форма без права отправить обещала бы
 * то, чего не будет. Отказ сервера (лимит тарифа, нет компании)
 * приходит ошибкой на поле и остаётся рядом с формой.
 */
function RespondCard({ listingId, guest, owner }: { listingId: number; guest: boolean; owner: boolean }) {
    const form = useForm({ body: '' });
    const [open, setOpen] = useState(false);

    if (owner) {
        return null;
    }

    if (guest) {
        return (
            <div className="card">
                <Link href={routes.login} className="btn btn-primary btn-block">
                    <MessageSquareText aria-hidden className="size-4" /> {t('listing.respond')}
                </Link>
                <p className="t-caption muted mt-8">{t('listing.respond_login')}</p>
            </div>
        );
    }

    function submit(e: React.FormEvent) {
        e.preventDefault();
        form.post(routes.listingRespond(listingId), { preserveScroll: true });
    }

    return (
        <div className="card">
            {open ? (
                <form onSubmit={submit}>
                    <label className="label" htmlFor="respond-body">
                        {t('listing.respond')}
                    </label>
                    <textarea
                        id="respond-body"
                        className="textarea"
                        style={{ minHeight: 96 }}
                        maxLength={2000}
                        autoFocus
                        placeholder={t('listing.respond_placeholder')}
                        value={form.data.body}
                        onChange={(e) => form.setData('body', e.target.value)}
                    />
                    {form.errors.body && (
                        <p className="hint" style={{ color: 'var(--danger)' }}>
                            {form.errors.body}
                        </p>
                    )}
                    <button
                        type="submit"
                        className="btn btn-primary btn-block mt-12"
                        disabled={form.processing || form.data.body.trim() === ''}
                    >
                        {form.processing ? t('listing.respond_sending') : t('listing.respond_send')}
                    </button>
                    <p className="t-caption muted mt-8">{t('listing.respond_note')}</p>
                </form>
            ) : (
                <>
                    <button className="btn btn-primary btn-block" onClick={() => setOpen(true)}>
                        <MessageSquareText aria-hidden className="size-4" /> {t('listing.respond')}
                    </button>
                    <p className="t-caption muted mt-8">{t('listing.respond_hint')}</p>
                </>
            )}
        </div>
    );
}
