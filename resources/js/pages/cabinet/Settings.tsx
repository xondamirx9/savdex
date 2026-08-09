import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Panel } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';

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
    security: { two_factor: boolean; last_login_at: string | null; last_login_ip: string | null };
    is_owner: boolean;
}

const LOCALES = [
    ['ru', 'Русский'],
    ['uz', 'Oʻzbekcha'],
    ['en', 'English'],
    ['zh', '中文'],
    ['tr', 'Türkçe'],
];

export default function Settings({ profile, notifications, security, is_owner }: Props) {
    const [rows, setRows] = useState(notifications);
    const [confirmDelete, setConfirmDelete] = useState(false);

    const notify = useForm<{ notifications: Notification[] }>({ notifications });
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
        <CabinetLayout title="Настройки" heading="Настройки">
            <div className="grid grid-2">
                <Panel title="Уведомления">
                    <div className="table-wrap" style={{ border: 'none' }}>
                        <table className="table" style={{ minWidth: 0 }}>
                            <thead>
                                <tr>
                                    <th>Событие</th>
                                    <th className="center">Почта</th>
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
                                                aria-label={`${r.label} — почта`}
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
                    <p className="t-sm muted mt-16">Изменения сохраняются сразу.</p>
                </Panel>

                <div className="stack-16">
                    <Panel title="Профиль">
                        <div className="field">
                            <label className="label" htmlFor="s-name">
                                Имя
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
                                Телефон
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
                                    {profile.phone_verified ? 'Подтверждён' : 'Не подтверждён'}. При смене номера
                                    подтверждение сбрасывается.
                                </p>
                            )}
                        </div>

                        <div className="field">
                            <label className="label" htmlFor="s-locale">
                                Язык интерфейса
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
                            <label className="label">Почта</label>
                            <p className="t-sm">
                                {profile.email}{' '}
                                {profile.email_verified ? (
                                    <span className="badge badge-verified">подтверждена</span>
                                ) : (
                                    <Link href={routes.verifyNotice} className="badge badge-warning">
                                        подтвердить
                                    </Link>
                                )}
                            </p>
                        </div>

                        <button
                            className="btn btn-primary mt-16"
                            disabled={form.processing}
                            onClick={() => form.patch(routes.cabinetSettings + '/profile', { preserveScroll: true })}
                        >
                            Сохранить
                        </button>
                    </Panel>

                    <Panel title="Безопасность">
                        <div className="row-between" style={{ marginBottom: 16, gap: 12 }}>
                            <div>
                                <b>Двухфакторная аутентификация</b>
                                <p className="t-sm muted">Код из приложения при входе</p>
                            </div>
                            {/* Отключённая кнопка без объяснения читается как
                                поломка. Пока двухфакторной нет — говорим об этом */}
                            <span className="badge badge-neutral">скоро</span>
                        </div>

                        {security.last_login_at && (
                            <p className="t-sm muted" style={{ marginBottom: 16 }}>
                                Последний вход: {security.last_login_at}
                                {security.last_login_ip && ` с адреса ${security.last_login_ip}`}
                            </p>
                        )}

                        <Link href={routes.passwordRequest} className="btn btn-secondary btn-block">
                            <ShieldCheck aria-hidden className="size-4" /> Сменить пароль
                        </Link>
                    </Panel>

                    {/* Удаление владельца снимает объявления всей компании,
                        поэтому предупреждение конкретное, а не «данные будут удалены» */}
                    <div className="card" style={{ borderColor: 'rgba(220,38,38,.3)' }}>
                        <h2 className="t-h3" style={{ marginBottom: 8, color: 'var(--danger)' }}>
                            Удаление аккаунта
                        </h2>
                        <p className="t-sm muted" style={{ marginBottom: 16 }}>
                            {is_owner
                                ? 'Вы владелец компании: все её объявления будут сняты с публикации. История платежей сохранится по требованию закона.'
                                : 'Ваш доступ будет закрыт. Объявления компании останутся у остальных сотрудников.'}
                        </p>

                        {confirmDelete ? (
                            <>
                                <div className="field">
                                    <label className="label" htmlFor="s-pass">
                                        Введите пароль для подтверждения
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
                                        Удалить навсегда
                                    </button>
                                    <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(false)}>
                                        Отмена
                                    </button>
                                </div>
                            </>
                        ) : (
                            <button className="btn btn-danger btn-sm" onClick={() => setConfirmDelete(true)}>
                                Удалить аккаунт
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </CabinetLayout>
    );
}
