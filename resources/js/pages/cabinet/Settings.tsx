import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Send, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Panel } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';
import { t } from '@/lib/i18n';

interface Notification {
    event: string;
    label: string;
    email: boolean;
    telegram: boolean;
}

interface Props {
    profile: {
        name: string;
        email: string;
        phone: string | null;
        locale: string;
        email_verified: boolean;
        phone_verified: boolean;
    };
    notifications: Notification[];
    telegram: { available: boolean; linked: boolean; username: string | null };
    security: { two_factor: boolean; last_login_at: string | null; last_login_ip: string | null };
    is_owner: boolean;
}

// Языки названы на самих себе — переводить их нельзя
const LOCALES = [
    ['ru', 'Русский'],
    ['uz', 'Oʻzbekcha'],
    ['en', 'English'],
    ['zh', '中文'],
    ['tr', 'Türkçe'],
];

export default function Settings({ profile, notifications, telegram, security, is_owner }: Props) {
    const [rows, setRows] = useState(notifications);
    const [confirmDelete, setConfirmDelete] = useState(false);

    const notify = useForm<{ notifications: Notification[] }>({ notifications });
    const link = useForm({});
    const unlink = useForm({});
    const form = useForm({ name: profile.name, phone: profile.phone ?? '', locale: profile.locale });
    const remove = useForm({ password: '' });

    function toggle(event: string, channel: 'email' | 'telegram') {
        const next = rows.map((r) => (r.event === event ? { ...r, [channel]: !r[channel] } : r));
        setRows(next);

        // transform, а не setData: setData обновляет состояние асинхронно,
        // и запрос ушёл бы с прежними значениями
        notify.transform(() => ({ notifications: next }));
        notify.patch(routes.cabinetSettings + '/notifications', { preserveScroll: true });
    }

    return (
        <CabinetLayout title={t('cabinet.settings.title')} heading={t('cabinet.settings.title')}>
            <div className="grid grid-2">
                <Panel title={t('cabinet.settings.notifications')}>
                    <div className="table-wrap" style={{ border: 'none' }}>
                        <table className="table" style={{ minWidth: 0 }}>
                            <thead>
                                <tr>
                                    <th>{t('cabinet.settings.event')}</th>
                                    <th className="center">{t('cabinet.settings.email')}</th>
                                    <th className="center">Telegram</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.event}>
                                        <td>{r.label}</td>
                                        <td className="center">
                                            <input
                                                type="checkbox"
                                                aria-label={t('cabinet.settings.email_aria', { label: r.label })}
                                                checked={r.email}
                                                onChange={() => toggle(r.event, 'email')}
                                            />
                                        </td>
                                        <td className="center">
                                            <input
                                                type="checkbox"
                                                aria-label={`${r.label} — Telegram`}
                                                checked={r.telegram}
                                                onChange={() => toggle(r.event, 'telegram')}
                                            />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="t-sm muted mt-16">{t('cabinet.settings.saved_instantly')}</p>
                </Panel>

                <div className="stack-16">
                    <Panel title={t('cabinet.settings.profile')}>
                        <div className="field">
                            <label className="label" htmlFor="s-name">
                                {t('cabinet.settings.name')}
                            </label>
                            <input
                                id="s-name"
                                className="input"
                                value={form.data.name}
                                onChange={(e) => form.setData('name', e.target.value)}
                            />
                            {form.errors.name && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.name}</p>}
                        </div>

                        <div className="field">
                            <label className="label" htmlFor="s-phone">
                                {t('cabinet.settings.phone')}
                            </label>
                            <input
                                id="s-phone"
                                className="input"
                                value={form.data.phone}
                                onChange={(e) => form.setData('phone', e.target.value)}
                            />
                            {form.errors.phone ? (
                                <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.phone}</p>
                            ) : (
                                <p className="hint">
                                    {profile.phone_verified ? t('cabinet.settings.phone_verified') : t('cabinet.settings.phone_unverified')}{t('cabinet.settings.phone_note')}
                                </p>
                            )}
                        </div>

                        <div className="field">
                            <label className="label" htmlFor="s-locale">
                                {t('cabinet.settings.language')}
                            </label>
                            <select
                                id="s-locale"
                                className="select"
                                value={form.data.locale}
                                onChange={(e) => form.setData('locale', e.target.value)}
                            >
                                {LOCALES.map(([code, label]) => (
                                    <option key={code} value={code}>
                                        {label}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div className="field">
                            <label className="label">{t('cabinet.settings.email')}</label>
                            <p className="t-sm">
                                {profile.email}{' '}
                                {profile.email_verified ? (
                                    <span className="badge badge-verified">{t('cabinet.settings.email_verified')}</span>
                                ) : (
                                    <Link href={routes.verifyNotice} className="badge badge-warning">
                                        {t('cabinet.settings.email_verify')}
                                    </Link>
                                )}
                            </p>
                        </div>

                        <button
                            className="btn btn-primary mt-16"
                            disabled={form.processing}
                            onClick={() => form.patch(routes.cabinetSettings + '/profile', { preserveScroll: true })}
                        >
                            {t('cabinet.settings.save')}
                        </button>
                    </Panel>

                    {/* Telegram — не украшение: это второй способ вернуть
                        доступ, когда рабочая почта потеряна вместе
                        с сотрудником, который её заводил */}
                    {telegram.available && (
                        <Panel title={t('cabinet.settings.telegram_title')}>
                            <p className="t-sm muted" style={{ marginBottom: 16 }}>
                                {t('cabinet.settings.telegram_lead')}
                            </p>

                            {telegram.linked ? (
                                <div className="row-between" style={{ gap: 12 }}>
                                    <span>
                                        <span className="badge badge-supply">{t('cabinet.settings.telegram_linked')}</span>
                                        {telegram.username && <b className="ml-8">@{telegram.username}</b>}
                                    </span>
                                    <button
                                        type="button"
                                        className="btn btn-secondary"
                                        onClick={() =>
                                            unlink.delete(routes.cabinetSettings + '/telegram', { preserveScroll: true })
                                        }
                                    >
                                        {t('cabinet.settings.telegram_disconnect')}
                                    </button>
                                </div>
                            ) : (
                                <>
                                    {/* Не ссылка на бот, а запрос к серверу:
                                        одноразовый токен привязки выдаётся
                                        в момент нажатия и живёт 15 минут */}
                                    <button
                                        type="button"
                                        className="btn btn-secondary btn-block"
                                        onClick={() => link.post(routes.cabinetSettings + '/telegram')}
                                        disabled={link.processing}
                                    >
                                        <Send aria-hidden className="size-4" />{' '}
                                        {t('cabinet.settings.telegram_connect')}
                                    </button>
                                    <p className="t-sm muted mt-8">{t('cabinet.settings.telegram_hint')}</p>
                                </>
                            )}
                        </Panel>
                    )}

                    <Panel title={t('cabinet.settings.security')}>
                        <div className="row-between" style={{ marginBottom: 16, gap: 12 }}>
                            <div>
                                <b>{t('cabinet.settings.two_factor')}</b>
                                <p className="t-sm muted">{t('cabinet.settings.two_factor_text')}</p>
                            </div>
                            {/* Отключённая кнопка без объяснения читается как
                                поломка. Пока двухфакторной нет — говорим об этом */}
                            <span className="badge badge-neutral">{t('cabinet.settings.soon')}</span>
                        </div>

                        {security.last_login_at && (
                            <p className="t-sm muted" style={{ marginBottom: 16 }}>
                                {t('cabinet.settings.last_login', { date: security.last_login_at })}
                                {security.last_login_ip && ` ${t('cabinet.settings.last_login_ip', { ip: security.last_login_ip })}`}
                            </p>
                        )}

                        <Link href={routes.passwordRequest} className="btn btn-secondary btn-block">
                            <ShieldCheck aria-hidden className="size-4" /> {t('cabinet.settings.change_password')}
                        </Link>
                    </Panel>

                    {/* Удаление владельца снимает объявления всей компании,
                        поэтому предупреждение конкретное, а не «данные будут удалены» */}
                    <div className="card" style={{ borderColor: 'rgba(220,38,38,.3)' }}>
                        <h2 className="t-h3" style={{ marginBottom: 8, color: 'var(--danger)' }}>
                            {t('cabinet.settings.delete_title')}
                        </h2>
                        <p className="t-sm muted" style={{ marginBottom: 16 }}>
                            {is_owner
                                ? t('cabinet.settings.delete_owner')
                                : t('cabinet.settings.delete_member')}
                        </p>

                        {confirmDelete ? (
                            <>
                                <div className="field">
                                    <label className="label" htmlFor="s-pass">
                            {t('cabinet.settings.delete_password')}
                                    </label>
                                    <input
                                        id="s-pass"
                                        className="input"
                                        type="password"
                                        autoFocus
                                        value={remove.data.password}
                                        onChange={(e) => remove.setData('password', e.target.value)}
                                    />
                                    {remove.errors.password && (
                                        <p className="hint" style={{ color: 'var(--danger)' }}>{remove.errors.password}</p>
                                    )}
                                </div>
                                <div className="row" style={{ gap: 10 }}>
                                    <button
                                        className="btn btn-danger btn-sm"
                                        disabled={remove.processing}
                                        onClick={() => remove.post(routes.cabinetSettings + '/delete')}
                                    >
                                        {t('cabinet.settings.delete_forever')}
                                    </button>
                                    <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(false)}>
                                        {t('common.cancel')}
                                    </button>
                                </div>
                            </>
                        ) : (
                            <button className="btn btn-danger btn-sm" onClick={() => setConfirmDelete(true)}>
                                {t('cabinet.settings.delete_account')}
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </CabinetLayout>
    );
}
