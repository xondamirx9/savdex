import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Check, Eye, FileText, Info, Pencil, Plus, Trash2, Upload, X } from 'lucide-react';
import { useRef, useState } from 'react';
import { useConfirm } from '@/components/useConfirm';
import { FileUploadModal } from '@/components/cabinet/FileUploadModal';
import { Panel, Tabs } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

interface Company {
    id: number;
    name: string;
    slug: string;
    legal_name: string | null;
    tin: string | null;
    country_id: number | null;
    city_id: number | null;
    address: string | null;
    custom_category: string | null;
    description: string | null;
    website: string | null;
    founded_year: number | null;
    employees_range: string | null;
    type: string | null;
    primary_role: string | null;
    is_it_provider: boolean;
    it_specializations: string[];
    initials: string;
    logo: string | null;
    cover: string | null;
    completeness: number;
    missing: string[];
    verification_level: number;
}

interface Props {
    company: Company | null;
    serviceTypes: Record<string, string>;
    contacts: { id: number; type: string; value: string; label: string | null; is_public: boolean }[];
    documents: {
        id: number;
        type: string;
        type_label: string;
        title: string;
        status: string;
        size: string | null;
        is_material: boolean;
        is_public: boolean;
        valid_until: string | null;
        missing: boolean;
    }[];
    employees: { id: number; name: string; email: string; role: string; verified: boolean }[];
    countries: { id: number; name: string }[];
    cities: { id: number; name: string; country_id: number }[];
    verification: { label: string; done: boolean; hint: string | null }[];
    plan: { name: string; verification_days: number; has_microsite: boolean } | null;
}

const EMPLOYEE_RANGES = ['1-10', '10-50', '50-100', '100-500', '500+'];
const TYPES = ['manufacturer', 'distributor', 'trader', 'retailer'];

export default function CompanyProfile({
    company,
    serviceTypes,
    contacts,
    documents,
    employees,
    countries,
    cities,
    verification,
    plan,
}: Props) {
    const [tab, setTab] = useState('main');
    /** Какой тип файла предзаполнить в форме загрузки; null — форма закрыта */
    const [uploading, setUploading] = useState<string | null>(null);
    const logoInput = useRef<HTMLInputElement>(null);
    const coverInput = useRef<HTMLInputElement>(null);
    const { confirm, dialog } = useConfirm();

    const form = useForm<{
        name: string;
        legal_name: string;
        tin: string;
        country_id: number | null;
        city_id: number | null;
        address: string;
        description: string;
        website: string;
        founded_year: number | null;
        employees_range: string;
        type: string;
        custom_category: string;
        primary_role: string;
        is_it_provider: boolean;
        it_specializations: string[];
    }>({
        name: company?.name ?? '',
        legal_name: company?.legal_name ?? '',
        tin: company?.tin ?? '',
        country_id: company?.country_id ?? countries[0]?.id ?? null,
        city_id: company?.city_id ?? null,
        address: company?.address ?? '',
        description: company?.description ?? '',
        website: company?.website ?? '',
        founded_year: company?.founded_year ?? null,
        employees_range: company?.employees_range ?? '',
        type: company?.type ?? 'distributor',
        custom_category: company?.custom_category ?? '',
        primary_role: company?.primary_role ?? 'both',
        is_it_provider: company?.is_it_provider ?? false,
        it_specializations: company?.it_specializations ?? [],
    });

    const descRef = useRef<HTMLTextAreaElement>(null);

    /* Правки текста идут через setData, а не execCommand: форма должна
       знать о каждом изменении, иначе кнопка «Сохранить» отправит старое */
    function wrapSelection(before: string, after: string) {
        const el = descRef.current;
        if (!el) return;
        const { selectionStart: a, selectionEnd: b, value } = el;
        const selected = value.slice(a, b) || t('cabinet.company.sample_text');
        form.setData('description', value.slice(0, a) + before + selected + after + value.slice(b));
        requestAnimationFrame(() => {
            el.focus();
            el.setSelectionRange(a + before.length, a + before.length + selected.length);
        });
    }

    /*
     * Контакты компании: добавление и правка одной формой. Телефон,
     * который клиент указал при регистрации, раньше нельзя было ни
     * сменить, ни убрать — серверные маршруты существовали, а кнопок
     * не было.
     */
    const [contactEditor, setContactEditor] = useState<number | 'new' | null>(null);
    const contactForm = useForm({ type: 'phone', value: '', label: '' });

    function openContactEditor(c?: { id: number; type: string; value: string; label: string | null }) {
        contactForm.clearErrors();
        contactForm.setData(c ? { type: c.type, value: c.value, label: c.label ?? '' } : { type: 'phone', value: '', label: '' });
        setContactEditor(c ? c.id : 'new');
    }

    function submitContact() {
        const options = {
            preserveScroll: true,
            onSuccess: () => {
                setContactEditor(null);
                contactForm.reset();
            },
        };

        if (contactEditor === 'new') {
            contactForm.post(routes.companyContacts, options);
        } else if (typeof contactEditor === 'number') {
            contactForm.patch(routes.companyContact(contactEditor), options);
        }
    }

    function insertAtCursor(snippet: string) {
        const el = descRef.current;
        if (!el) return;
        const { selectionStart: a, value } = el;
        form.setData('description', value.slice(0, a) + snippet + value.slice(a));
        requestAnimationFrame(() => {
            el.focus();
            el.setSelectionRange(a + snippet.length, a + snippet.length);
        });
    }

    const availableCities = cities.filter((c) => c.country_id === form.data.country_id);

    function submit() {
        form.patch(routes.cabinetCompany, { preserveScroll: true });
    }

    const tabs = [
        { key: 'main', label: t('cabinet.company.tab_main') },
        { key: 'docs', label: t('cabinet.company.tab_docs') },
        { key: 'files', label: t('cabinet.company.tab_files'), count: documents.length },
        { key: 'site', label: t('cabinet.company.tab_site') },
        { key: 'staff', label: t('cabinet.company.tab_staff'), count: employees.length },
    ];

    return (
        <CabinetLayout
            title={t('cabinet.company.title')}
            heading={company ? t('cabinet.company.title') : t('cabinet.company.title_new')}
            subheading={
                company
                    ? t('cabinet.company.filled', { percent: company.completeness })
                    : t('cabinet.company.subtitle_new')
            }
            actions={
                company ? (
                    <Link href={routes.company(company.slug)} className="btn btn-secondary">
                        <Eye aria-hidden className="size-4" /> {t('cabinet.company.preview')}
                    </Link>
                ) : undefined
            }
        >
            {dialog}

            {company && (
                <div className="progress" style={{ marginBottom: 24 }}>
                    <div className="progress-fill" style={{ width: `${company.completeness}%` }} />
                </div>
            )}

            {company && <Tabs items={tabs} active={tab} onChange={setTab} label={t('cabinet.company.tabs_label')} />}

            {(!company || tab === 'main') && (
                <div className="card" style={{ maxWidth: 720 }}>
                    {company && (
                        <div className="row" style={{ gap: 20, marginBottom: 24, alignItems: 'flex-start' }}>
                            <span className="listing-logo logo-64" style={{ width: 88, height: 88, fontSize: 26 }}>
                                {company.logo ? <img src={company.logo} alt="" /> : company.initials}
                            </span>
                            <div>
                                <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                                    <button
                                        className="btn btn-secondary btn-sm"
                                        type="button"
                                        onClick={() => logoInput.current?.click()}
                                    >
                                        <Upload aria-hidden className="size-4" />
                                        {company.logo
                                            ? t('cabinet.company.logo_replace')
                                            : t('cabinet.company.logo_upload')}
                                    </button>
                                    {company.logo && (
                                        <button
                                            className="btn btn-ghost btn-sm"
                                            type="button"
                                            onClick={() =>
                                                confirm({
                                                    title: t('cabinet.company.logo_delete_title'),
                                                    description: t('cabinet.company.logo_delete_text'),
                                                    confirmLabel: t('common.delete'),
                                                    danger: true,
                                                    onConfirm: () =>
                                                        router.delete('/cabinet/company/logo', { preserveScroll: true }),
                                                })
                                            }
                                        >
                                            {t('common.delete')}
                                        </button>
                                    )}
                                </div>
                                <input
                                    ref={logoInput}
                                    type="file"
                                    accept="image/jpeg,image/png,image/webp"
                                    hidden
                                    onChange={(e) => {
                                        const file = e.target.files?.[0];
                                        if (!file) return;
                                        router.post(
                                            '/cabinet/company/logo',
                                            { logo: file },
                                            { preserveScroll: true, forceFormData: true },
                                        );
                                        e.target.value = '';
                                    }}
                                />
                                <p className="hint">{t('cabinet.company.logo_hint')}</p>
                            </div>
                        </div>
                    )}

                    {company && (
                        <div style={{ marginBottom: 24 }}>
                            <div
                                style={{
                                    height: 96,
                                    borderRadius: 12,
                                    marginBottom: 10,
                                    background: company.cover
                                        ? `url(${company.cover}) center/cover`
                                        : 'linear-gradient(120deg,var(--primary-700),var(--primary-500))',
                                }}
                            />
                            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                                <button
                                    className="btn btn-secondary btn-sm"
                                    type="button"
                                    onClick={() => coverInput.current?.click()}
                                >
                                    <Upload aria-hidden className="size-4" />
                                    {company.cover
                                        ? t('cabinet.company.cover_replace')
                                        : t('cabinet.company.cover_upload')}
                                </button>
                                {company.cover && (
                                    <button
                                        className="btn btn-ghost btn-sm"
                                        type="button"
                                        onClick={() =>
                                            confirm({
                                                title: t('cabinet.company.cover_delete_title'),
                                                description: t('cabinet.company.cover_delete_text'),
                                                confirmLabel: t('common.delete'),
                                                danger: true,
                                                onConfirm: () =>
                                                    router.delete('/cabinet/company/cover', { preserveScroll: true }),
                                            })
                                        }
                                    >
                                        {t('common.delete')}
                                    </button>
                                )}
                            </div>
                            <input
                                ref={coverInput}
                                type="file"
                                accept="image/jpeg,image/png,image/webp"
                                hidden
                                onChange={(e) => {
                                    const file = e.target.files?.[0];
                                    if (!file) return;
                                    router.post(
                                        '/cabinet/company/cover',
                                        { cover: file },
                                        { preserveScroll: true, forceFormData: true },
                                    );
                                    e.target.value = '';
                                }}
                            />
                            <p className="hint">{t('cabinet.company.cover_hint')}</p>
                        </div>
                    )}

                    <div className="field">
                        <label className="label" htmlFor="p-name">
                            {t('cabinet.company.name')} <span className="req">*</span>
                        </label>
                        <input
                            id="p-name"
                            className="input"
                            value={form.data.name}
                            onChange={(e) => form.setData('name', e.target.value)}
                            placeholder={t('cabinet.company.name_placeholder')}
                        />
                        {form.errors.name && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.name}</p>}
                    </div>

                    <div className="field">
                        <label className="label" htmlFor="p-legal">
                            {t('cabinet.company.legal_name')}
                        </label>
                        <input
                            id="p-legal"
                            className="input"
                            value={form.data.legal_name}
                            onChange={(e) => form.setData('legal_name', e.target.value)}
                        />
                    </div>

                    <div className="grid grid-2 grid-tight" style={{ gap: 12 }}>
                        <div className="field" style={{ margin: 0 }}>
                            <label className="label" htmlFor="p-tin">
                                {t('cabinet.company.tin')}
                            </label>
                            <input
                                id="p-tin"
                                className="input"
                                value={form.data.tin}
                                onChange={(e) => form.setData('tin', e.target.value)}
                            />
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                            <label className="label" htmlFor="p-year">
                                {t('cabinet.company.founded')}
                            </label>
                            <input
                                id="p-year"
                                className="input"
                                type="number"
                                value={form.data.founded_year ?? ''}
                                onChange={(e) => form.setData('founded_year', e.target.value ? Number(e.target.value) : null)}
                            />
                            {form.errors.founded_year && (
                                <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.founded_year}</p>
                            )}
                        </div>
                    </div>

                    <div className="grid grid-2 grid-tight mt-16" style={{ gap: 12 }}>
                        <div className="field" style={{ margin: 0 }}>
                            <label className="label" htmlFor="p-country">
                                {t('cabinet.company.country')}
                            </label>
                            <select
                                id="p-country"
                                className="select"
                                value={form.data.country_id ?? ''}
                                onChange={(e) => {
                                    form.setData('country_id', e.target.value ? Number(e.target.value) : null);
                                    form.setData('city_id', null);
                                }}
                            >
                                <option value="">{t('cabinet.company.country_none')}</option>
                                {countries.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                            <label className="label" htmlFor="p-city">
                                {t('cabinet.company.city')}
                            </label>
                            <select
                                id="p-city"
                                className="select"
                                value={form.data.city_id ?? ''}
                                onChange={(e) => form.setData('city_id', e.target.value ? Number(e.target.value) : null)}
                            >
                                <option value="">{t('cabinet.company.city_none')}</option>
                                {availableCities.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>

                    <div className="field mt-16">
                        <label className="label" htmlFor="p-addr">
                            {t('cabinet.company.address')}
                        </label>
                        <input
                            id="p-addr"
                            className="input"
                            value={form.data.address}
                            onChange={(e) => form.setData('address', e.target.value)}
                            placeholder={t('cabinet.company.address_placeholder')}
                        />
                        <p className="hint">{t('cabinet.company.address_hint')}</p>
                    </div>

                    <div className="grid grid-2 grid-tight" style={{ gap: 12 }}>
                        <div className="field" style={{ margin: 0 }}>
                            <label className="label" htmlFor="p-type">
                                {t('cabinet.company.type')}
                            </label>
                            <select
                                id="p-type"
                                className="select"
                                value={form.data.type ?? ''}
                                onChange={(e) => form.setData('type', e.target.value)}
                            >
                                {TYPES.map((value) => (
                                    <option key={value} value={value}>
                                        {t(`cabinet.company.type_${value}`)}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                            <label className="label" htmlFor="p-emp">
                                {t('cabinet.company.employees')}
                            </label>
                            <select
                                id="p-emp"
                                className="select"
                                value={form.data.employees_range ?? ''}
                                onChange={(e) => form.setData('employees_range', e.target.value)}
                            >
                                <option value="">{t('cabinet.company.not_set')}</option>
                                {EMPLOYEE_RANGES.map((r) => (
                                    <option key={r} value={r}>
                                        {r}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>

                    <div className="field mt-16">
                        <label className="label" htmlFor="p-custom-cat">
                            {t('cabinet.company.custom_category')}
                        </label>
                        <input
                            id="p-custom-cat"
                            className="input"
                            maxLength={80}
                            value={form.data.custom_category}
                            onChange={(e) => form.setData('custom_category', e.target.value)}
                            placeholder={t('cabinet.company.custom_category_placeholder')}
                        />
                        <p className="hint">{t('cabinet.company.custom_category_hint')}</p>
                    </div>

                    <div className="field mt-16">
                        <label className="label" htmlFor="p-site">
                            {t('cabinet.company.website')}
                        </label>
                        <input
                            id="p-site"
                            className="input"
                            value={form.data.website}
                            onChange={(e) => form.setData('website', e.target.value)}
                            placeholder="company.uz"
                        />
                    </div>

                    <div className="field">
                        <label className="label" htmlFor="p-desc">
                            {t('cabinet.company.description')}
                        </label>
                        {/* Панель форматирования: жирный, галочка, список.
                            Разметку понимает визитка (см. lib/richtext) */}
                        <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                            <button type="button" className="btn btn-secondary btn-sm" title={t('cabinet.company.bold')}
                                onClick={() => wrapSelection('**', '**')}>
                                <b>{t('cabinet.company.bold_letter')}</b>
                            </button>
                            <button type="button" className="btn btn-secondary btn-sm" title={t('cabinet.company.check')}
                                onClick={() => insertAtCursor('✔ ')}>
                                ✔
                            </button>
                            <button type="button" className="btn btn-secondary btn-sm" title={t('cabinet.company.bullet')}
                                onClick={() => insertAtCursor('\n- ')}>
                                •&nbsp;{t('cabinet.company.list')}
                            </button>
                        </div>
                        <textarea
                            id="p-desc"
                            ref={descRef}
                            className="textarea"
                            style={{ minHeight: 140 }}
                            value={form.data.description}
                            onChange={(e) => form.setData('description', e.target.value)}
                            placeholder={t('cabinet.company.description_placeholder')}
                        />
                        <p className="hint">{t('cabinet.company.description_hint')}</p>
                    </div>

                    {/* Роль IT-исполнителя: только с ней видна кнопка «Откликнуться»
                        в разделе «IT-услуги». Специализации показываются на визитке
                        и помогают заказчику понять, к кому обращаться */}
                    <div className="field mt-24" style={{ paddingTop: 20, borderTop: '1px solid var(--border)' }}>
                        <label className="check">
                            <input
                                type="checkbox"
                                checked={form.data.is_it_provider}
                                onChange={(e) => form.setData('is_it_provider', e.target.checked)}
                            />
                            {t('cabinet.company.it_provider')}
                        </label>
                        <p className="hint">{t('cabinet.company.it_provider_hint')}</p>
                        {form.data.is_it_provider && (
                            <div className="row wrap mt-12" style={{ gap: 8 }}>
                                {Object.entries(serviceTypes).map(([code, label]) => {
                                    const on = form.data.it_specializations.includes(code);
                                    return (
                                        <button
                                            key={code}
                                            type="button"
                                            className={cn('chip', on && 'chip-active')}
                                            aria-pressed={on}
                                            onClick={() =>
                                                form.setData(
                                                    'it_specializations',
                                                    on
                                                        ? form.data.it_specializations.filter((c) => c !== code)
                                                        : [...form.data.it_specializations, code],
                                                )
                                            }
                                        >
                                            {label}
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                        {form.errors.it_specializations && (
                            <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.it_specializations}</p>
                        )}
                    </div>

                    <button className="btn btn-primary mt-24" type="button" disabled={form.processing} onClick={submit}>
                        {company ? t('cabinet.company.save') : t('cabinet.company.create')}
                    </button>
                </div>
            )}

            {company && tab === 'docs' && (
                <div className="card" style={{ maxWidth: 720 }}>
                    <h3 className="t-h3">{t('cabinet.company.verification')}</h3>
                    <p className="t-sm muted mt-8" style={{ marginBottom: 20 }}>
                        {t('cabinet.company.verification_now')}{' '}
                        {company.verification_level > 1 ? (
                            <span className="badge badge-gold">{t('cabinet.company.level_2')}</span>
                        ) : company.verification_level > 0 ? (
                            <span className="badge badge-verified">{t('cabinet.company.level_1')}</span>
                        ) : (
                            <span className="badge badge-neutral">{t('cabinet.company.level_0')}</span>
                        )}
                    </p>

                    <ul className="stack-12">
                        {verification.map((v) => (
                            <li key={v.label} className="row" style={{ gap: 10 }}>
                                {v.done ? (
                                    <Check aria-hidden className="size-5 shrink-0" style={{ color: 'var(--success)' }} />
                                ) : (
                                    <X aria-hidden className="size-5 shrink-0" style={{ color: 'var(--border-strong)' }} />
                                )}
                                <span className={v.done ? undefined : 'muted'}>
                                    {v.label}
                                    {v.hint && ` — ${v.hint}`}
                                </span>
                            </li>
                        ))}
                    </ul>

                    <div className="alert alert-info mt-24">
                        <Info aria-hidden className="size-5" />
                        <div>
                            {t('cabinet.company.review_time', { plan: plan?.name ?? '' })}{' '}
                            <b>{tChoice('cabinet.company.working_days', plan?.verification_days ?? 1)}</b>
                            {t('cabinet.company.review_note')}
                        </div>
                    </div>

                    <button className="btn btn-primary mt-24" onClick={() => setUploading('registration')}>
                        <Upload aria-hidden className="size-4" /> {t('cabinet.company.upload_document')}
                    </button>
                </div>
            )}

            {company && tab === 'files' && (
                <div className="card" style={{ maxWidth: 820 }}>
                    <div className="row-between wrap" style={{ gap: 12, marginBottom: 6 }}>
                        <div>
                            <h3 className="t-h3">{t('cabinet.company.files')}</h3>
                            <p className="t-sm muted mt-8">{t('cabinet.company.files_text')}</p>
                        </div>
                        <button className="btn btn-primary" onClick={() => setUploading('presentation')}>
                            <Upload aria-hidden className="size-4" /> {t('cabinet.files.upload_file')}
                        </button>
                    </div>

                    {documents.length === 0 ? (
                        <div className="empty" style={{ padding: '40px 0' }}>
                            <div className="empty-icon">
                                <FileText aria-hidden className="size-7" />
                            </div>
                            <p className="t-h4">{t('cabinet.company.files_empty')}</p>
                            <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                                {t('cabinet.company.files_empty_text')}
                            </p>
                        </div>
                    ) : (
                        <div className="mt-24">
                            {documents.map((d) => (
                                <div key={d.id} className="file-row">
                                    <span className="ico-box ico-box-sm shrink-0">
                                        <FileText aria-hidden className="size-4" />
                                    </span>

                                    <span style={{ flex: 1, minWidth: 0 }}>
                                        <a href={`/files/${d.id}`} className="file-title">
                                            {d.title}
                                        </a>
                                        <span className="t-caption muted">
                                            {d.type_label}
                                            {d.size && ` · ${d.size}`}
                                            {d.valid_until &&
                                                ` · ${t('cabinet.company.valid_until', { date: d.valid_until })}`}
                                        </span>
                                    </span>

                                    {/* Файл пропал при обновлении сайта: запись осталась,
                                        содержимого нет — просим загрузить заново */}
                                    {d.missing && (
                                        <span className="badge badge-danger shrink-0">
                                            {t('cabinet.company.file_missing')}
                                        </span>
                                    )}

                                    {/* Документы проходят модерацию, материалы — нет:
                                        статус показываем только там, где он есть */}
                                    {!d.is_material && !d.missing && (
                                        <span
                                            className={cn(
                                                'badge shrink-0',
                                                d.status === 'approved'
                                                    ? 'badge-verified'
                                                    : d.status === 'rejected'
                                                      ? 'badge-danger'
                                                      : 'badge-neutral',
                                            )}
                                        >
                                            {d.status === 'approved'
                                                ? t('cabinet.company.doc_approved')
                                                : d.status === 'rejected'
                                                  ? t('cabinet.company.doc_rejected')
                                                  : t('cabinet.company.doc_pending')}
                                        </span>
                                    )}

                                    <label className="check shrink-0" title={t('cabinet.files.public')}>
                                        <input
                                            type="checkbox"
                                            checked={d.is_public}
                                            onChange={(e) =>
                                                router.patch(
                                                    `/cabinet/company/files/${d.id}`,
                                                    { is_public: e.target.checked },
                                                    { preserveScroll: true },
                                                )
                                            }
                                        />
                                        <span className="hide-mobile">{t('cabinet.company.on_card')}</span>
                                    </label>

                                    <button
                                        className="btn btn-ghost btn-icon shrink-0"
                                        aria-label={t('cabinet.company.delete_file_aria', { title: d.title })}
                                        onClick={() =>
                                            confirm({
                                                title: t('cabinet.company.delete_file_title', { title: d.title }),
                                                description: d.is_public
                                                    ? t('cabinet.company.delete_file_public')
                                                    : t('cabinet.company.delete_file_text'),
                                                confirmLabel: t('common.delete'),
                                                danger: true,
                                                onConfirm: () =>
                                                    router.delete(`/cabinet/company/files/${d.id}`, { preserveScroll: true }),
                                            })
                                        }
                                    >
                                        <Trash2 aria-hidden className="size-5" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            <FileUploadModal
                open={uploading !== null}
                initialType={uploading ?? 'presentation'}
                onClose={() => setUploading(null)}
            />

            {company && tab === 'site' && (
                <Panel>
                    {plan?.has_microsite ? (
                        <p className="muted">{t('cabinet.company.microsite_soon')}</p>
                    ) : (
                        <>
                            <p className="muted">{t('cabinet.company.microsite_plan')}</p>
                            <Link href={routes.pricing} className="btn btn-outline mt-16">
                                {t('cabinet.company.compare_plans')}
                            </Link>
                        </>
                    )}
                </Panel>
            )}

            {company && tab === 'staff' && (
                <Panel
                    title={t('cabinet.company.staff')}
                    /* Кнопка была отключена и молчала о причине. Пояснение
                       и так есть внизу раздела — дублировать его значком
                       честнее, чем показывать мёртвую кнопку */
                    action={<span className="badge badge-neutral">{t('cabinet.company.invites_soon')}</span>}
                >
                    <div className="table-wrap table-cards" style={{ border: 'none' }}>
                        <table className="table" style={{ minWidth: 0 }}>
                            <thead>
                                <tr>
                                    <th>{t('cabinet.company.col_name')}</th>
                                    <th>{t('cabinet.company.col_email')}</th>
                                    <th>{t('cabinet.company.col_role')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {employees.map((e) => (
                                    <tr key={e.id}>
                                        <td data-label={t('cabinet.company.col_name')}>
                                            <b>{e.name}</b>
                                        </td>
                                        <td data-label={t('cabinet.company.col_email')}>
                                            {e.email}
                                            {!e.verified && (
                                                <span className="badge badge-warning">
                                                    {t('cabinet.company.email_unverified')}
                                                </span>
                                            )}
                                        </td>
                                        <td data-label={t('cabinet.company.col_role')}>{e.role}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <p className="t-sm muted mt-16">{t('cabinet.company.staff_note')}</p>
                </Panel>
            )}

            {company && tab === 'main' && (
                <Panel
                    title={t('cabinet.company.contacts')}
                    className="mt-24"
                    action={
                        <button className="btn btn-secondary btn-sm" type="button" onClick={() => openContactEditor()}>
                            <Plus aria-hidden className="size-4" /> {t('cabinet.company.contact_add')}
                        </button>
                    }
                >
                    {contacts.length > 0 && (
                        <ul className="stack-12">
                            {contacts.map((c) => (
                                <li key={c.id} className="row-between" style={{ gap: 10 }}>
                                    <span className="t-sm" style={{ minWidth: 0 }}>
                                        <b>{c.value}</b>
                                        {c.label && <span className="muted"> · {c.label}</span>}
                                    </span>
                                    <span className="row" style={{ gap: 6, flexShrink: 0 }}>
                                        <span className="badge badge-neutral hide-mobile">
                                            {c.is_public
                                                ? t('cabinet.company.contact_public')
                                                : t('cabinet.company.contact_paid')}
                                        </span>
                                        <button
                                            className="btn btn-ghost btn-sm"
                                            type="button"
                                            aria-label={t('cabinet.company.contact_edit')}
                                            onClick={() => openContactEditor(c)}
                                        >
                                            <Pencil aria-hidden className="size-4" />
                                        </button>
                                        <button
                                            className="btn btn-ghost btn-sm"
                                            type="button"
                                            aria-label={t('cabinet.company.contact_delete')}
                                            onClick={() =>
                                                confirm({
                                                    title: t('cabinet.company.contact_delete_title'),
                                                    description: t('cabinet.company.contact_delete_text', {
                                                        value: c.value,
                                                    }),
                                                    confirmLabel: t('common.delete'),
                                                    danger: true,
                                                    onConfirm: () => router.delete(routes.companyContact(c.id), { preserveScroll: true }),
                                                })
                                            }
                                        >
                                            <Trash2 aria-hidden className="size-4" />
                                        </button>
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}

                    {contactEditor !== null && (
                        <div className="card card--pad-sm mt-16" style={{ background: 'var(--bg)' }}>
                            <div className="grid grid-2 grid-tight" style={{ gap: 12 }}>
                                <div className="field" style={{ margin: 0 }}>
                                    <label className="label" htmlFor="ct-type">
                                        {t('cabinet.company.contact_type')}
                                    </label>
                                    <select
                                        id="ct-type"
                                        className="select"
                                        value={contactForm.data.type}
                                        onChange={(e) => contactForm.setData('type', e.target.value)}
                                    >
                                        <option value="phone">{t('cabinet.company.contact_phone')}</option>
                                        <option value="email">{t('cabinet.company.contact_email')}</option>
                                        <option value="telegram">Telegram</option>
                                        <option value="whatsapp">WhatsApp</option>
                                        <option value="website">{t('cabinet.company.website')}</option>
                                    </select>
                                </div>
                                <div className="field" style={{ margin: 0 }}>
                                    <label className="label" htmlFor="ct-value">
                                        {t('cabinet.company.contact_value')}
                                    </label>
                                    <input
                                        id="ct-value"
                                        className="input"
                                        value={contactForm.data.value}
                                        onChange={(e) => contactForm.setData('value', e.target.value)}
                                        placeholder={contactForm.data.type === 'phone' ? '+998 90 123-45-67' : 'sales@company.uz'}
                                    />
                                    {contactForm.errors.value && (
                                        <p className="hint" style={{ color: 'var(--danger)' }}>{contactForm.errors.value}</p>
                                    )}
                                </div>
                            </div>
                            <div className="field mt-12" style={{ margin: 0 }}>
                                <label className="label" htmlFor="ct-label">
                                    {t('cabinet.company.contact_label')}
                                </label>
                                <input
                                    id="ct-label"
                                    className="input"
                                    value={contactForm.data.label}
                                    onChange={(e) => contactForm.setData('label', e.target.value)}
                                    placeholder={t('cabinet.company.contact_label_placeholder')}
                                />
                            </div>
                            <div className="row mt-16" style={{ gap: 8 }}>
                                <button className="btn btn-primary btn-sm" type="button" disabled={contactForm.processing} onClick={submitContact}>
                                    {contactEditor === 'new' ? t('cabinet.company.contact_add_short') : t('common.save')}
                                </button>
                                <button className="btn btn-ghost btn-sm" type="button" onClick={() => setContactEditor(null)}>
                                    {t('common.cancel')}
                                </button>
                            </div>
                        </div>
                    )}

                    <p className="t-sm muted mt-16">{t('cabinet.company.contacts_note')}</p>
                </Panel>
            )}
        </CabinetLayout>
    );
}
