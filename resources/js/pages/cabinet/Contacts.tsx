import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { BadgeCheck, Download, Info, Search, Star, TriangleAlert, Users } from 'lucide-react';
import { useState } from 'react';
import { Empty } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';
import { t, tChoice } from '@/lib/i18n';

interface Row {
    id: number;
    company: { name: string | null; slug: string | null; initials: string | null; verified: number; city: string | null };
    phones: string[];
    emails: string[];
    listing: string | null;
    opened_at: string;
    status: string;
    status_label: string;
    note: string | null;
    can_review: boolean;
    complaint_status: string | null;
    moderator_note: string | null;
    refunded: boolean;
}

interface Props {
    contacts: Row[];
    statuses: Record<string, string>;
    filters: { q: string; status: string };
}

export default function Contacts({ contacts, statuses, filters }: Props) {
    const [q, setQ] = useState(filters.q);
    const [editing, setEditing] = useState<number | null>(null);
    const [note, setNote] = useState('');
    const [complaining, setComplaining] = useState<number | null>(null);
    const complaint = useForm({ reason: '' });

    function filter(next: Partial<{ q: string; status: string }>) {
        router.get(
            routes.cabinetContacts,
            { q, status: filters.status, ...next },
            { preserveState: true, preserveScroll: true, replace: true },
        );
    }

    function saveNote(id: number) {
        router.patch(`/cabinet/contacts/${id}`, { note }, { preserveScroll: true, onSuccess: () => setEditing(null) });
    }

    function changeStatus(id: number, status: string) {
        router.patch(`/cabinet/contacts/${id}`, { status }, { preserveScroll: true });
    }

    return (
        <CabinetLayout
            title={t('cabinet.contacts.title')}
            heading={t('cabinet.contacts.title')}
            subheading={t('cabinet.contacts.subheading', { companies: tChoice('cabinet.contacts.companies', contacts.length) })}
            actions={
                contacts.length > 0 ? (
                    <a href="/cabinet/contacts/export" className="btn btn-secondary">
                        <Download aria-hidden className="size-4" /> {t('cabinet.contacts.export')}
                    </a>
                ) : undefined
            }
        >
            {contacts.length === 0 && !filters.q && !filters.status ? (
                <Empty
                    icon={Users}
                    title={t('cabinet.contacts.empty_title')}
                    text={t('cabinet.contacts.empty_text')}
                    action={{ href: routes.companies, label: t('cabinet.contacts.empty_action') }}
                />
            ) : (
                <>
                    <div className="toolbar">
                        <div style={{ position: 'relative', flex: 1, minWidth: 220 }}>
                            <label htmlFor="c-q" className="sr-only">
                            {t('cabinet.contacts.search_label')}
                            </label>
                            <input
                                id="c-q"
                                className="input"
                                type="search"
                                placeholder={t('cabinet.contacts.search_placeholder')}
                                style={{ paddingLeft: 42 }}
                                value={q}
                                onChange={(e) => setQ(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && filter({ q })}
                                onBlur={() => filter({ q })}
                            />
                            <span
                                aria-hidden
                                style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
                            >
                                <Search className="size-5" />
                            </span>
                        </div>
                        <select
                            className="select"
                            style={{ width: 'auto', minWidth: 180 }}
                            aria-label={t('cabinet.contacts.status')}
                            value={filters.status}
                            onChange={(e) => filter({ status: e.target.value })}
                        >
                            <option value="">{t('cabinet.contacts.status_all')}</option>
                            {Object.entries(statuses).map(([key, label]) => (
                                <option key={key} value={key}>
                                    {label}
                                </option>
                            ))}
                        </select>
                    </div>

                    {contacts.length === 0 ? (
                        <div className="card empty">
                            <p className="t-h4">{t('cabinet.contacts.nothing_title')}</p>
                            <p className="t-sm muted mt-8">{t('cabinet.contacts.nothing_text')}</p>
                        </div>
                    ) : (
                        <div className="table-wrap table-cards">
                            <table className="table table-contacts">
                                <thead>
                                    <tr>
                                        <th>{t('cabinet.contacts.company')}</th>
                                        <th>{t('cabinet.contacts.listing')}</th>
                                        <th>{t('cabinet.contacts.opened')}</th>
                                        <th>{t('cabinet.contacts.status')}</th>
                                        <th>{t('cabinet.contacts.note')}</th>
                                        <th>
                                            <span className="sr-only">{t('cabinet.contacts.actions')}</span>
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {contacts.map((row) => (
                                        <tr key={row.id}>
                                            <td data-label={t('cabinet.contacts.company')}>
                                                <div className="row" style={{ gap: 10 }}>
                                                    <span className="listing-logo logo-32">{row.company.initials}</span>
                                                    <span style={{ minWidth: 0 }}>
                                                        <b>
                                                            {row.company.slug ? (
                                                                <Link href={routes.company(row.company.slug)}>
                                                                    {row.company.name}
                                                                </Link>
                                                            ) : (
                                                                row.company.name
                                                            )}
                                                        </b>
                                                        {row.company.verified > 0 && (
                                                            <>
                                                                {' '}
                                                                <span className="badge badge-verified">
                                                                    <BadgeCheck aria-hidden className="size-3.5" />
                                                                </span>
                                                            </>
                                                        )}
                                                        <br />
                                                        {/* Контакты показываются целиком — они оплачены */}
                                                        <span className="t-caption muted contact-values">
                                                            {row.phones.map((p) => (
                                                                <a key={p} href={`tel:${p.replace(/[\s-]/g, '')}`}>
                                                                    {p}
                                                                </a>
                                                            ))}
                                                            {row.emails.map((e) => (
                                                                <a key={e} href={`mailto:${e}`}>
                                                                    {e}
                                                                </a>
                                                            ))}
                                                        </span>
                                                    </span>
                                                </div>
                                            </td>

                                            <td data-label={t('cabinet.contacts.listing')}>
                                                <span className="t-sm">{row.listing ?? '—'}</span>
                                            </td>
                                            <td data-label={t('cabinet.contacts.opened')}>{row.opened_at}</td>

                                            <td data-label={t('cabinet.contacts.status')}>
                                                <select
                                                    className="select"
                                                    style={{ height: 32, fontSize: 13, width: 'auto' }}
                                                    aria-label={t('cabinet.contacts.status_aria', { company: row.company.name ?? '' })}
                                                    value={row.status}
                                                    onChange={(e) => changeStatus(row.id, e.target.value)}
                                                >
                                                    {Object.entries(statuses).map(([key, label]) => (
                                                        <option key={key} value={key}>
                                                            {label}
                                                        </option>
                                                    ))}
                                                </select>
                                            </td>

                                            <td data-label={t('cabinet.contacts.note')}>
                                                {editing === row.id ? (
                                                    <div className="row" style={{ gap: 6 }}>
                                                        <input
                                                            className="input"
                                                            style={{ height: 34, fontSize: 13 }}
                                                            value={note}
                                                            autoFocus
                                                            onChange={(e) => setNote(e.target.value)}
                                                            onKeyDown={(e) => {
                                                                if (e.key === 'Enter') saveNote(row.id);
                                                                if (e.key === 'Escape') setEditing(null);
                                                            }}
                                                        />
                                                        <button className="btn btn-primary btn-sm" onClick={() => saveNote(row.id)}>
                                                    {t('cabinet.contacts.ok')}
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <button
                                                        className="t-sm muted"
                                                        style={{ textAlign: 'left' }}
                                                        onClick={() => {
                                                            setEditing(row.id);
                                                            setNote(row.note ?? '');
                                                        }}
                                                    >
                                                        {row.note || <span style={{ opacity: 0.6 }}>{t('cabinet.contacts.add_note')}</span>}
                                                    </button>
                                                )}
                                            </td>

                                            <td data-label="">
                                                <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                                                    {row.can_review && (
                                                        <button
                                                            className="btn btn-ghost btn-icon"
                                                            aria-label={t('cabinet.contacts.review_aria', { company: row.company.name ?? '' })}
                                                            title={t('cabinet.contacts.review')}
                                                        >
                                                            <Star aria-hidden className="size-5" />
                                                        </button>
                                                    )}
                                                    {row.complaint_status === 'pending' ? (
                                                        <span className="badge badge-neutral">{t('cabinet.contacts.complaint_pending')}</span>
                                                    ) : row.complaint_status === 'accepted' ? (
                                                        /* Возврат — то, что обещали при подаче жалобы.
                                                           Показываем результат, а не вечное «на проверке» */
                                                        <span
                                                            className="badge badge-verified"
                                                            title={row.moderator_note ?? undefined}
                                                        >
                                                            {row.refunded ? t('cabinet.contacts.complaint_refunded') : t('cabinet.contacts.complaint_accepted')}
                                                        </span>
                                                    ) : row.complaint_status === 'declined' ? (
                                                        <span
                                                            className="badge badge-warning"
                                                            title={row.moderator_note ?? undefined}
                                                        >
                                                            {t('cabinet.contacts.complaint_rejected')}
                                                        </span>
                                                    ) : (
                                                        <button
                                                            className="btn btn-ghost btn-icon"
                                                            aria-label={t('cabinet.contacts.complain_aria', { company: row.company.name ?? '' })}
                                                            title={t('cabinet.contacts.complain_title')}
                                                            onClick={() => {
                                                                setComplaining(row.id);
                                                                complaint.reset();
                                                            }}
                                                        >
                                                            <TriangleAlert aria-hidden className="size-5" />
                                                        </button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {complaining !== null && (
                        <div className="card mt-24" style={{ borderColor: 'var(--danger)' }}>
                            <h2 className="t-h4" style={{ marginBottom: 12 }}>
                            {t('cabinet.contacts.complain_heading')}
                            </h2>
                            <textarea
                                className="textarea"
                                style={{ minHeight: 90 }}
                                value={complaint.data.reason}
                                onChange={(e) => complaint.setData('reason', e.target.value)}
                                placeholder={t('cabinet.contacts.complain_placeholder')}
                            />
                            {complaint.errors.reason && (
                                <p className="hint" style={{ color: 'var(--danger)' }}>
                                    {complaint.errors.reason}
                                </p>
                            )}
                            <div className="row mt-16" style={{ gap: 10 }}>
                                <button
                                    className="btn btn-primary"
                                    disabled={complaint.processing}
                                    onClick={() =>
                                        complaint.post(`/cabinet/contacts/${complaining}/complaint`, {
                                            preserveScroll: true,
                                            onSuccess: () => setComplaining(null),
                                        })
                                    }
                                >
                                {t('cabinet.contacts.complain_send')}
                                </button>
                                <button className="btn btn-ghost" onClick={() => setComplaining(null)}>
                                {t('common.cancel')}
                                </button>
                            </div>
                        </div>
                    )}

                    <div className="alert alert-info mt-24">
                        <Info aria-hidden className="size-5" />
                        <div>
                            {t('cabinet.contacts.complain_hint')}
                        </div>
                    </div>
                </>
            )}
        </CabinetLayout>
    );
}
