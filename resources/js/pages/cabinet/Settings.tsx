import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Send, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Panel } from '@/components/cabinet';
import { CompanyInfoPanel } from '@/components/cabinet/CompanyInfoPanel';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';
import { SelectField } from '@/components/SelectField';
import { cn } from '@/lib/cn';
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
    /** Категории компании: по ним бот присылает новинки; null — компании ещё нет */
    categories: {
        options: { id: number; name: string }[];
        selected: number[];
        max: number;
        editable: boolean;
    } | null;
    /** Новые объявления и тендеры в Telegram не на паузе */
    feed: boolean;
}

// Языки названы на самих себе — переводить их нельзя
const LOCALES = [
    ['ru', 'Русский'],
    ['uz', 'O‘zbekcha'],
    ['en', 'English'],
    ['zh', '中文'],
    ['tr', 'Türkçe'],
];

export default function Settings({ profile, notifications, telegram, security, is_owner, categories, feed }: Props) {
    const [rows, setRows] = useState(notifications);
    const [chosen, setChosen] = useState(categories?.selected ?? []);
    const [feedOn, setFeedOn] = useState(feed);
    const [confirmDelete, setConfirmDelete] = useState(false);

    const notify = useForm<{ notifications: Notification[] }>({ notifications });
    const link = useForm({});
    const unlink = useForm({});
    const form = useForm({ name: profile.name, phone: profile.phone ?? '', locale: profile.locale });
    const remove = useForm({ password: '' });
    const pick = useForm<{ categories: number[] }>({ categories: chosen });
    const feedForm = useForm<{ on: boolean }>({ on: feed });

    // Кнопка «Изменить категории» из бота ведёт на #categories: страница
    // рисуется в браузере, и сам браузер до блока не докручивает
    useEffect(() => {
        if (window.location.hash === '#categories') {
            document.getElementById('categories')?.scrollIntoView({ block: 'start' });
        }
    }, []);

    function toggleCategory(id: number) {
        if (!categories?.editable) return;

        const next = chosen.includes(id) ? chosen.filter((c) => c !== id) : [...chosen, id];

        if (next.length > categories.max) return;

        setChosen(next);
        pick.transform(() => ({ categories: next }));
        pick.patch(routes.cabinetSettings + '/categories', {
            preserveScroll: true,
            // Сервер не принял — вернуть, как было
            onError: () => setChosen(chosen),
        });
    }

    function toggleFeed() {
        const next = !feedOn;
        setFeedOn(next);
        feedForm.transform(() => ({ on: next }));
        feedForm.patch(routes.cabinetSettings + '/telegram-feed', { preserveScroll: true });
    }

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
                <div className="stack-16">
                    <Panel title={t('cabinet.settings.notifications')}>
                        <div className="table-wrap" style={{ border: 'none' }}>
                            <table className="table" style={{ minWidth: 0 }}>
                                <thead>
                                    <tr>
                                        <th>{t('cabinet.settings.event')}</th>
                                        <th className="center">{t('cabinet.settings.email')}</th>
                                        {/* Бот не настроен — столбец обещал бы то, чего нет */}
                                        {telegram.available && <th className="center">Telegram</th>}
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
                                            {telegram.available && (
                                                <td className="center">
                                                    {/* Пока Telegram не привязан, отмечать нечего — ниже кнопка привязки */}
                                                    <input
                                                        type="checkbox"
                                                        aria-label={`${r.label} — Telegram`}
                                                        checked={r.telegram && telegram.linked}
                                                        disabled={!telegram.linked}
                                                        onChange={() => toggle(r.event, 'telegram')}
                                                    />
                                                </td>
                                            )}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <p className="t-sm muted mt-16">{t('cabinet.settings.saved_instantly')}</p>
                    </Panel>

                    {/* Сюда ведёт кнопка «Изменить категории» из бота */}
                    {categories && (
                        <div id="categories">
                            <Panel title={t('cabinet.settings.categories_title')}>
                                <p className="t-sm muted" style={{ marginBottom: 12 }}>
                                    {t('cabinet.settings.categories_lead')}
                                </p>
                                <div className="row wrap" style={{ gap: 6 }}>
                                    {categories.options.map((c) => {
                                        const active = chosen.includes(c.id);
                                        const full = !active && chosen.length >= categories.max;

                                        return (
                                            <button
                                                key={c.id}
                                                type="button"
                                                className={cn('chip', active && 'chip-active')}
                                                aria-pressed={active}
                                                disabled={!categories.editable || full || pick.processing}
                                                onClick={() => toggleCategory(c.id)}
                                            >
                                                {c.name}
                                            </button>
                                        );
                                    })}
                                </div>
                                {pick.errors.categories && (
                                    <p className="hint" style={{ color: 'var(--danger)' }}>{pick.errors.categories}</p>
                                )}
                                <p className="t-sm muted mt-16">
                                    {chosen.length === 0
                                        ? t('cabinet.settings.categories_empty')
                                        : categories.editable
                                          ? t('cabinet.settings.categories_hint', { max: categories.max })
                                          : t('cabinet.settings.categories_owner_note')}
                                </p>
                            </Panel>
                        </div>
                    )}

                    {/* Данные компании меняет только владелец: сотрудник
                        видит их на странице «Компания» */}
                    {is_owner && <CompanyInfoPanel />}
                </div>

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
                            <SelectField
                                id="s-locale"
                                ariaLabel={t('cabinet.settings.language')}
                                value={form.data.locale}
                                onChange={(value) => form.setData('locale', value)}
                                options={LOCALES.map(([code, label]) => ({ value: code, label }))}
                            />
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

                            {telegram.linked && (
                                <label className="row" style={{ gap: 8, marginBottom: 16 }}>
                                    <input
                                        type="checkbox"
                                        checked={feedOn}
                                        disabled={feedForm.processing}
                                        onChange={toggleFeed}
                                    />
                                    <span>{t('cabinet.settings.feed_label')}</span>
                                </label>
                            )}

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
