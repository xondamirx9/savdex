import { CheckCircle2, Clock, LifeBuoy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { SelectField } from '@/components/SelectField';
import { Panel } from '@/components/cabinet';
import { cn } from '@/lib/cn';
import { COMPANY_TYPES, EMPLOYEE_RANGES, isFilled } from '@/lib/companyOptions';
import { t, tChoice } from '@/lib/i18n';
import { localize } from '@/lib/locale';
import { CityField, type CityValue } from '@/components/CityField';
import { countryCode, tinLabel, type CountryOption } from '@/lib/countries';
import { routes } from '@/routes';

interface CompanyInfo {
    name: string;
    legal_name: string | null;
    tin: string | null;
    country_id: number | null;
    city_id: CityValue;
    /** «Другой город»: название текстом (python/savdex/web/city_choice.py). */
    city_name?: string;
    address: string | null;
    employees_range: string | null;
    founded_year: number | null;
    type: string | null;
    description: string | null;
    is_it_provider: boolean;
    it_specializations: string[];
}

interface Payload {
    company: CompanyInfo;
    /** До какой даты заполненное менять нельзя; null — можно сейчас */
    locked_until: string | null;
    /** Реквизиты со сроком смены; у физлица и фрилансера — пусто */
    locked_fields: string[];
    changed_at: string | null;
    cooldown_months: number;
    /** Дней до конца срока; null — менять можно сейчас */
    days_left: number | null;
    /** Какая часть срока прошла, 0…1 */
    cooldown_progress: number | null;
    /** С какого дня откроется следующая смена, если сохранить сейчас */
    next_if_changed: string;
    countries: CountryOption[];
    cities: { id: number; name: string; country_id: number }[];
    serviceTypes: Record<string, string>;
}

type Errors = Partial<Record<keyof CompanyInfo | 'message', string>>;

const ENDPOINT = `${routes.cabinetSettings}/company-info`;

/** Запрос JSON к Laravel: токен из куки XSRF, как у автосохранения мастера объявлений. */
async function request(method: string, url: string, body?: unknown): Promise<Response> {
    const token = document.cookie.match(/XSRF-TOKEN=([^;]+)/)?.[1];

    return fetch(localize(url), {
        method,
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            ...(token ? { 'X-XSRF-TOKEN': decodeURIComponent(token) } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
}

/** Первая ошибка каждого поля из ответа 422. */
function firstErrors(errors: Record<string, string[]> | undefined): Errors {
    return Object.fromEntries(Object.entries(errors ?? {}).map(([k, v]) => [k.split('.')[0], v[0]]));
}

/**
 * «Данные компании» в настройках профиля.
 *
 * Заполненные сведения меняются раз в полгода; пока срок не вышел,
 * они только читаются, а рядом — форма обращения в поддержку. Данные
 * грузятся и сохраняются отдельными запросами: страницу настроек на
 * боевом отдаёт Django, а этот блок живёт у Laravel.
 */
export function CompanyInfoPanel() {
    const [payload, setPayload] = useState<Payload | null>(null);
    const [failed, setFailed] = useState(false);
    const [data, setData] = useState<CompanyInfo | null>(null);
    const [errors, setErrors] = useState<Errors>({});
    const [notice, setNotice] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);

    const [support, setSupport] = useState('');
    const [supportError, setSupportError] = useState<string | null>(null);
    const [supportSent, setSupportSent] = useState<string | null>(null);
    const [sending, setSending] = useState(false);

    useEffect(() => {
        request('GET', ENDPOINT)
            .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
            .then((json: Payload) => {
                setPayload(json);
                setData(json.company);
            })
            .catch(() => setFailed(true));
    }, []);

    if (failed) {
        return (
            <Panel title={t('cabinet.settings.company_title')}>
                <p className="t-sm muted">{t('cabinet.settings.company_load_failed')}</p>
            </Panel>
        );
    }

    if (!payload || !data) {
        return (
            <Panel title={t('cabinet.settings.company_title')}>
                <p className="t-sm muted">{t('cabinet.settings.company_loading')}</p>
            </Panel>
        );
    }

    const original = payload.company;
    const cooling = payload.locked_until !== null;
    // В срок блокировки заполненные реквизиты только читаются, пустые — можно
    // заполнить; остальные сведения меняются когда угодно
    const limited = payload.locked_fields.length > 0;
    const isLockedField = (field: keyof CompanyInfo) => payload.locked_fields.includes(field);
    const locked = (field: keyof CompanyInfo) => cooling && isLockedField(field) && isFilled(original[field]);
    const set = <K extends keyof CompanyInfo>(field: K, value: CompanyInfo[K]) =>
        setData((d) => (d ? { ...d, [field]: value } : d));
    const cities = payload.cities.filter((c) => c.country_id === data.country_id);
    const changesFilled = (Object.keys(original) as (keyof CompanyInfo)[]).some(
        (f) => isLockedField(f) && isFilled(original[f]) && JSON.stringify(original[f]) !== JSON.stringify(data[f]),
    );

    async function save() {
        // Смена заполненного запускает полгода ожидания — спросить заранее
        if (changesFilled && !window.confirm(t('cabinet.settings.company_confirm'))) return;

        setSaving(true);
        setErrors({});
        setNotice(null);

        try {
            const res = await request('PATCH', ENDPOINT, data);
            const json = await res.json();

            if (res.ok) {
                setPayload(json);
                setData(json.company);
                setNotice(json.message);
            } else {
                setErrors({ ...firstErrors(json.errors), message: json.message });
            }
        } catch {
            setErrors({ message: t('cabinet.settings.company_load_failed') });
        } finally {
            setSaving(false);
        }
    }

    async function sendSupport() {
        setSending(true);
        setSupportError(null);

        try {
            const res = await request('POST', `${ENDPOINT}/support`, { message: support });
            const json = await res.json();

            if (res.ok) {
                setSupportSent(json.message);
                setSupport('');
            } else {
                setSupportError(json.errors?.message?.[0] ?? json.message);
            }
        } catch {
            setSupportError(t('cabinet.settings.company_load_failed'));
        } finally {
            setSending(false);
        }
    }

    const error = (field: keyof CompanyInfo) =>
        errors[field] && <p className="hint" style={{ color: 'var(--danger)' }}>{errors[field]}</p>;

    return (
        <Panel title={t('cabinet.settings.company_title')}>
            {/* У физлица и фрилансера срока смены нет — и плашек о нём тоже */}
            {limited && (
                <p className="t-sm muted" style={{ marginBottom: 16 }}>
                    {t('cabinet.settings.company_lead')}
                </p>
            )}

            {/* Срок смены данных: сколько осталось или что будет после сохранения */}
            {!limited ? null : cooling ? (
                <div className="cooldown-card is-locked" role="status">
                    <div className="cooldown-card-head">
                        <Clock aria-hidden className="size-5" />
                        <b>{t('cabinet.settings.company_cooldown_locked_title', { date: payload.locked_until ?? '' })}</b>
                    </div>
                    {payload.days_left !== null && (
                        <p className="cooldown-card-days">
                            {tChoice('cabinet.settings.company_cooldown_days_left', payload.days_left)}
                        </p>
                    )}
                    {payload.cooldown_progress !== null && (
                        <div
                            className="cooldown-bar"
                            role="progressbar"
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={Math.round(payload.cooldown_progress * 100)}
                        >
                            <span style={{ width: `${payload.cooldown_progress * 100}%` }} />
                        </div>
                    )}
                    {payload.changed_at && (
                        <p className="t-sm muted">
                            {t('cabinet.settings.company_changed_at', { date: payload.changed_at })}
                        </p>
                    )}
                </div>
            ) : (
                <div className="cooldown-card is-open" role="status">
                    <div className="cooldown-card-head">
                        <CheckCircle2 aria-hidden className="size-5" />
                        <b>{t('cabinet.settings.company_cooldown_open_title')}</b>
                    </div>
                    <p className="t-sm">
                        {t('cabinet.settings.company_cooldown_open_text', { date: payload.next_if_changed })}
                    </p>
                    {payload.changed_at && (
                        <p className="t-sm muted">
                            {t('cabinet.settings.company_changed_at', { date: payload.changed_at })}
                        </p>
                    )}
                </div>
            )}

            <div className="field">
                <label className="label" htmlFor="ci-name">
                    {t('cabinet.company.name')} <span className="req">*</span>
                </label>
                <input
                    id="ci-name"
                    className="input"
                    value={data.name}
                    disabled={locked('name')}
                    onChange={(e) => set('name', e.target.value)}
                />
                {error('name')}
            </div>

            <div className="field">
                <label className="label" htmlFor="ci-legal">
                    {t('cabinet.company.legal_name')}
                </label>
                <input
                    id="ci-legal"
                    className="input"
                    value={data.legal_name ?? ''}
                    disabled={locked('legal_name')}
                    onChange={(e) => set('legal_name', e.target.value)}
                />
                {error('legal_name')}
            </div>

            <div className="grid grid-2 grid-tight" style={{ gap: 12 }}>
                <div className="field" style={{ margin: 0 }}>
                    <label className="label" htmlFor="ci-tin">
                        {tinLabel(countryCode(payload.countries, data.country_id))}
                    </label>
                    <input
                        id="ci-tin"
                        className="input"
                        value={data.tin ?? ''}
                        disabled={locked('tin')}
                        onChange={(e) => set('tin', e.target.value)}
                    />
                    {error('tin')}
                </div>
                <div className="field" style={{ margin: 0 }}>
                    <label className="label" htmlFor="ci-year">
                        {t('cabinet.company.founded')}
                    </label>
                    <input
                        id="ci-year"
                        className="input"
                        type="number"
                        value={data.founded_year ?? ''}
                        disabled={locked('founded_year')}
                        onChange={(e) => set('founded_year', e.target.value ? Number(e.target.value) : null)}
                    />
                    {error('founded_year')}
                </div>
            </div>

            <div className="grid grid-2 grid-tight mt-16" style={{ gap: 12 }}>
                <div className="field" style={{ margin: 0 }}>
                    <label className="label" htmlFor="ci-country">
                        {t('cabinet.company.country')}
                    </label>
                    <SelectField
                        id="ci-country"
                        ariaLabel={t('cabinet.company.country')}
                        value={String(data.country_id ?? '')}
                        disabled={locked('country_id')}
                        onChange={(value) =>
                            setData((d) => (d ? { ...d, country_id: value ? Number(value) : null, city_id: null } : d))
                        }
                        placeholder={t('cabinet.company.country_none')}
                        options={payload.countries.map((c) => ({ value: String(c.id), label: c.name }))}
                    />
                    {error('country_id')}
                </div>
                <CityField
                    id="ci-city"
                    label={t('cabinet.company.city')}
                    cities={cities}
                    value={data.city_id}
                    name={data.city_name ?? ''}
                    onChange={(value) => set('city_id', value)}
                    onNameChange={(name) => set('city_name', name)}
                    placeholder={t('cabinet.company.city_none')}
                    error={errors.city_id?.[0]}
                    disabled={locked('city_id') || data.country_id === null}
                />
            </div>

            <div className="field mt-16">
                <label className="label" htmlFor="ci-addr">
                    {t('cabinet.company.address')}
                </label>
                <input
                    id="ci-addr"
                    className="input"
                    value={data.address ?? ''}
                    disabled={locked('address')}
                    onChange={(e) => set('address', e.target.value)}
                />
                {error('address')}
            </div>

            <div className="grid grid-2 grid-tight" style={{ gap: 12 }}>
                <div className="field" style={{ margin: 0 }}>
                    <label className="label" htmlFor="ci-type">
                        {t('cabinet.company.type')}
                    </label>
                    <SelectField
                        id="ci-type"
                        ariaLabel={t('cabinet.company.type')}
                        value={data.type ?? ''}
                        disabled={locked('type')}
                        onChange={(value) => set('type', value)}
                        placeholder={t('cabinet.company.not_set')}
                        options={COMPANY_TYPES.map((value) => ({ value, label: t(`cabinet.company.type_${value}`) }))}
                    />
                </div>
                <div className="field" style={{ margin: 0 }}>
                    <label className="label" htmlFor="ci-emp">
                        {t('cabinet.company.employees')}
                    </label>
                    <SelectField
                        id="ci-emp"
                        ariaLabel={t('cabinet.company.employees')}
                        value={data.employees_range ?? ''}
                        disabled={locked('employees_range')}
                        onChange={(value) => set('employees_range', value)}
                        placeholder={t('cabinet.company.not_set')}
                        options={EMPLOYEE_RANGES.map((r) => ({ value: r, label: r }))}
                    />
                </div>
            </div>

            <div className="field mt-16">
                <label className="label" htmlFor="ci-desc">
                    {t('cabinet.company.description')}
                </label>
                <textarea
                    id="ci-desc"
                    className="textarea"
                    style={{ minHeight: 120 }}
                    value={data.description ?? ''}
                    disabled={locked('description')}
                    onChange={(e) => set('description', e.target.value)}
                />
                {error('description')}
            </div>

            <div className="field">
                <label className="check">
                    <input
                        type="checkbox"
                        checked={data.is_it_provider}
                        disabled={locked('is_it_provider')}
                        onChange={(e) => set('is_it_provider', e.target.checked)}
                    />
                    {t('cabinet.company.it_provider')}
                </label>
                {data.is_it_provider && (
                    <div className="row wrap mt-12" style={{ gap: 8 }}>
                        {Object.entries(payload.serviceTypes).map(([code, label]) => {
                            const on = data.it_specializations.includes(code);

                            return (
                                <button
                                    key={code}
                                    type="button"
                                    className={cn('chip', on && 'chip-active')}
                                    aria-pressed={on}
                                    disabled={locked('it_specializations')}
                                    onClick={() =>
                                        set(
                                            'it_specializations',
                                            on
                                                ? data.it_specializations.filter((c) => c !== code)
                                                : [...data.it_specializations, code],
                                        )
                                    }
                                >
                                    {label}
                                </button>
                            );
                        })}
                    </div>
                )}
                {error('it_specializations')}
            </div>

            {errors.message && (
                <p className="hint" role="alert" style={{ color: 'var(--danger)' }}>
                    {errors.message}
                </p>
            )}
            {notice && (
                <p className="hint" role="status" style={{ color: 'var(--success, #15803d)' }}>
                    {notice}
                </p>
            )}
            <button type="button" className="btn btn-primary mt-16" disabled={saving} onClick={save}>
                {t('cabinet.settings.company_save')}
            </button>

            {/* Пока срок не вышел — обращение в поддержку: оно попадает
                в раздел «Обращения» админки вместе с компанией и датой */}
            {cooling && (
                <div className="mt-24" style={{ paddingTop: 20, borderTop: '1px solid var(--border)' }}>
                    <h3 className="t-h4" style={{ marginBottom: 6 }}>
                        {t('cabinet.settings.company_support_title')}
                    </h3>
                    <p className="t-sm muted" style={{ marginBottom: 12 }}>
                        {t('cabinet.settings.company_support_text')}
                    </p>

                    {supportSent ? (
                        <div className="alert alert-info" role="status">
                            <LifeBuoy aria-hidden className="size-4" />
                            <span>{supportSent}</span>
                        </div>
                    ) : (
                        <>
                            <textarea
                                className="textarea"
                                aria-label={t('cabinet.settings.company_support_title')}
                                style={{ minHeight: 100 }}
                                maxLength={3000}
                                value={support}
                                placeholder={t('cabinet.settings.company_support_placeholder')}
                                onChange={(e) => setSupport(e.target.value)}
                            />
                            {supportError && (
                                <p className="hint" role="alert" style={{ color: 'var(--danger)' }}>
                                    {supportError}
                                </p>
                            )}
                            <button
                                type="button"
                                className="btn btn-secondary mt-12"
                                disabled={sending || support.trim() === ''}
                                onClick={sendSupport}
                            >
                                <LifeBuoy aria-hidden className="size-4" /> {t('cabinet.settings.company_support_send')}
                            </button>
                        </>
                    )}
                </div>
            )}
        </Panel>
    );
}
