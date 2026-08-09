import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { BadgeCheck, Download, Info, Search, Star, TriangleAlert, Users } from 'lucide-react';
import { useState } from 'react';
import { Empty } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { pluralize } from '@/lib/plural';
import { routes } from '@/routes';

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
            title="Мои контакты"
            heading="Мои контакты"
            subheading={`${pluralize(contacts.length, ['компания', 'компании', 'компаний'])}, контакты которых вы открыли. Доступны навсегда.`}
            actions={
                contacts.length > 0 ? (
                    <a href="/cabinet/contacts/export" className="btn btn-secondary">
                        <Download aria-hidden className="size-4" /> Выгрузить в CSV
                    </a>
                ) : undefined
            }
        >
            {contacts.length === 0 && !filters.q && !filters.status ? (
                <Empty
                    icon={Users}
                    title="Вы ещё не открывали контакты"
                    text="Найдите поставщика в каталоге и откройте его контакты за кредит. Доступ остаётся навсегда — платить второй раз за ту же компанию не придётся."
                    action={{ href: routes.companies, label: 'Открыть каталог компаний' }}
                />
            ) : (
                <>
                    <div className="toolbar">
                        <div style={{ position: 'relative', flex: 1, minWidth: 220 }}>
                            <label htmlFor="c-q" className="sr-only">
                                Поиск по контактам
                            </label>
                            <input
                                id="c-q"
                                className="input"
                                type="search"
                                placeholder="Поиск по компании или заметке"
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
                            aria-label="Статус"
                            value={filters.status}
                            onChange={(e) => filter({ status: e.target.value })}
                        >
                            <option value="">Все статусы</option>
                            {Object.entries(statuses).map(([key, label]) => (
                                <option key={key} value={key}>
                                    {label}
                                </option>
                            ))}
                        </select>
                    </div>

                    {contacts.length === 0 ? (
                        <div className="card empty">
                            <p className="t-h4">Ничего не найдено</p>
                            <p className="t-sm muted mt-8">Попробуйте изменить запрос или сбросить фильтр статуса.</p>
                        </div>
                    ) : (
                        <div className="table-wrap table-cards">
                            <table className="table table-contacts">
                                <thead>
                                    <tr>
                                        <th>Компания</th>
                                        <th>Объявление</th>
                                        <th>Открыт</th>
                                        <th>Статус</th>
                                        <th>Заметка</th>
                                        <th>
                                            <span className="sr-only">Действия</span>
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {contacts.map((row) => (
                                        <tr key={row.id}>
                                            <td data-label="Компания">
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

                                            <td data-label="Объявление">
                                                <span className="t-sm">{row.listing ?? '—'}</span>
                                            </td>
                                            <td data-label="Открыт">{row.opened_at}</td>

                                            <td data-label="Статус">
                                                <select
                                                    className="select"
                                                    style={{ height: 32, fontSize: 13, width: 'auto' }}
                                                    aria-label={`Статус контакта ${row.company.name}`}
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

                                            <td data-label="Заметка">
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
                                                            ОК
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
                                                        {row.note || <span style={{ opacity: 0.6 }}>+ заметка</span>}
                                                    </button>
                                                )}
                                            </td>

                                            <td data-label="">
                                                <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                                                    {row.can_review && (
                                                        <button
                                                            className="btn btn-ghost btn-icon"
                                                            aria-label={`Оставить отзыв о ${row.company.name}`}
                                                            title="Оставить отзыв"
                                                        >
                                                            <Star aria-hidden className="size-5" />
                                                        </button>
                                                    )}
                                                    {row.complaint_status === 'pending' ? (
                                                        <span className="badge badge-neutral">жалоба на проверке</span>
                                                    ) : row.complaint_status === 'accepted' ? (
                                                        /* Возврат — то, что обещали при подаче жалобы.
                                                           Показываем результат, а не вечное «на проверке» */
                                                        <span
                                                            className="badge badge-verified"
                                                            title={row.moderator_note ?? undefined}
                                                        >
                                                            {row.refunded ? 'списанное вернули' : 'жалоба принята'}
                                                        </span>
                                                    ) : row.complaint_status === 'declined' ? (
                                                        <span
                                                            className="badge badge-warning"
                                                            title={row.moderator_note ?? undefined}
                                                        >
                                                            жалоба отклонена
                                                        </span>
                                                    ) : (
                                                        <button
                                                            className="btn btn-ghost btn-icon"
                                                            aria-label={`Пожаловаться на контакт ${row.company.name}`}
                                                            title="Контакт нерабочий"
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
                                Что не так с контактом?
                            </h2>
                            <textarea
                                className="textarea"
                                style={{ minHeight: 90 }}
                                value={complaint.data.reason}
                                onChange={(e) => complaint.setData('reason', e.target.value)}
                                placeholder="Номер не отвечает третий день, почта возвращает ошибку доставки"
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
                                    Отправить жалобу
                                </button>
                                <button className="btn btn-ghost" onClick={() => setComplaining(null)}>
                                    Отмена
                                </button>
                            </div>
                        </div>
                    )}

                    <div className="alert alert-info mt-24">
                        <Info aria-hidden className="size-5" />
                        <div>
                            Контакт оказался нерабочим? Нажмите значок жалобы — при подтверждении вернём кредит на счёт.
                        </div>
                    </div>
                </>
            )}
        </CabinetLayout>
    );
}
