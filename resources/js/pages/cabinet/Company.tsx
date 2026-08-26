import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Check, Eye, FileText, Info, Trash2, Upload, X } from 'lucide-react';
import { useRef, useState } from 'react';
import { useConfirm } from '@/components/useConfirm';
import { FileUploadModal } from '@/components/cabinet/FileUploadModal';
import { Panel, Tabs } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { pluralize } from '@/lib/plural';
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
    description: string | null;
    website: string | null;
    founded_year: number | null;
    employees_range: string | null;
    type: string | null;
    primary_role: string | null;
    initials: string;
    logo: string | null;
    completeness: number;
    missing: string[];
    verification_level: number;
}

interface Props {
    company: Company | null;
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
    }[];
    employees: { id: number; name: string; email: string; role: string; verified: boolean }[];
    countries: { id: number; name: string }[];
    cities: { id: number; name: string; country_id: number }[];
    verification: { label: string; done: boolean; hint: string | null }[];
    plan: { name: string; verification_days: number; has_microsite: boolean } | null;
}

const EMPLOYEE_RANGES = ['1-10', '10-50', '50-100', '100-500', '500+'];
const TYPES = [
    ['manufacturer', 'Производитель'],
    ['distributor', 'Дистрибьютор'],
    ['trader', 'Трейдер'],
    ['retailer', 'Розница'],
];

export default function CompanyProfile({
    company,
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
        primary_role: string;
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
        primary_role: company?.primary_role ?? 'both',
    });

    const descRef = useRef<HTMLTextAreaElement>(null);

    /* Правки текста идут через setData, а не execCommand: форма должна
       знать о каждом изменении, иначе кнопка «Сохранить» отправит старое */
    function wrapSelection(before: string, after: string) {
        const el = descRef.current;
        if (!el) return;
        const { selectionStart: a, selectionEnd: b, value } = el;
        const selected = value.slice(a, b) || 'текст';
        form.setData('description', value.slice(0, a) + before + selected + after + value.slice(b));
        requestAnimationFrame(() => {
            el.focus();
            el.setSelectionRange(a + before.length, a + before.length + selected.length);
        });
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
        { key: 'main', label: 'Основное' },
        { key: 'docs', label: 'Верификация' },
        { key: 'files', label: 'Файлы и материалы', count: documents.length },
        { key: 'site', label: 'Мини-сайт' },
        { key: 'staff', label: 'Сотрудники', count: employees.length },
    ];

    return (
        <CabinetLayout
            title="Профиль компании"
            heading={company ? 'Профиль компании' : 'Данные компании'}
            subheading={company ? `Заполнен на ${company.completeness} %` : 'Заполните карточку — от её имени публикуются объявления'}
            actions={
                company ? (
                    <Link href={routes.company(company.slug)} className="btn btn-secondary">
                        <Eye aria-hidden className="size-4" /> Как видят другие
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

            {company && <Tabs items={tabs} active={tab} onChange={setTab} label="Разделы профиля" />}

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
                                        {company.logo ? 'Заменить логотип' : 'Загрузить логотип'}
                                    </button>
                                    {company.logo && (
                                        <button
                                            className="btn btn-ghost btn-sm"
                                            type="button"
                                            onClick={() =>
                                                confirm({
                                                    title: 'Удалить логотип?',
                                                    description: 'На визитке и в каталоге снова появятся инициалы компании.',
                                                    confirmLabel: 'Удалить',
                                                    danger: true,
                                                    onConfirm: () =>
                                                        router.delete('/cabinet/company/logo', { preserveScroll: true }),
                                                })
                                            }
                                        >
                                            Удалить
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
                                <p className="hint">
                                    Квадратное изображение, JPG, PNG или WebP до 8 МБ. Без логотипа
                                    на визитке показываются инициалы.
                                </p>
                            </div>
                        </div>
                    )}

                    <div className="field">
                        <label className="label" htmlFor="p-name">
                            Название <span className="req">*</span>
                        </label>
                        <input
                            id="p-name"
                            className="input"
                            value={form.data.name}
                            onChange={(e) => form.setData('name', e.target.value)}
                            placeholder="ООО «Стройбаза»"
                        />
                        {form.errors.name && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.name}</p>}
                    </div>

                    <div className="field">
                        <label className="label" htmlFor="p-legal">
                            Юридическое название
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
                                ИНН / СТИР
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
                                Год основания
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
                                Страна
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
                                <option value="">Не указана</option>
                                {countries.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                            <label className="label" htmlFor="p-city">
                                Город
                            </label>
                            <select
                                id="p-city"
                                className="select"
                                value={form.data.city_id ?? ''}
                                onChange={(e) => form.setData('city_id', e.target.value ? Number(e.target.value) : null)}
                            >
                                <option value="">Не указан</option>
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
                            Юридический адрес
                        </label>
                        <input
                            id="p-addr"
                            className="input"
                            value={form.data.address}
                            onChange={(e) => form.setData('address', e.target.value)}
                            placeholder="г. Ташкент, Мирзо-Улугбекский р-н, ул. …"
                        />
                        <p className="hint">Нужен для бейджа «Проверена+»</p>
                    </div>

                    <div className="grid grid-2 grid-tight" style={{ gap: 12 }}>
                        <div className="field" style={{ margin: 0 }}>
                            <label className="label" htmlFor="p-type">
                                Тип компании
                            </label>
                            <select
                                id="p-type"
                                className="select"
                                value={form.data.type ?? ''}
                                onChange={(e) => form.setData('type', e.target.value)}
                            >
                                {TYPES.map(([value, label]) => (
                                    <option key={value} value={value}>
                                        {label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="field" style={{ margin: 0 }}>
                            <label className="label" htmlFor="p-emp">
                                Сотрудников
                            </label>
                            <select
                                id="p-emp"
                                className="select"
                                value={form.data.employees_range ?? ''}
                                onChange={(e) => form.setData('employees_range', e.target.value)}
                            >
                                <option value="">Не указано</option>
                                {EMPLOYEE_RANGES.map((r) => (
                                    <option key={r} value={r}>
                                        {r}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>

                    <div className="field mt-16">
                        <label className="label" htmlFor="p-site">
                            Сайт
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
                            Описание компании
                        </label>
                        {/* Панель форматирования: жирный, галочка, список.
                            Разметку понимает визитка (см. lib/richtext) */}
                        <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                            <button type="button" className="btn btn-secondary btn-sm" title="Выделить жирным"
                                onClick={() => wrapSelection('**', '**')}>
                                <b>Ж</b>
                            </button>
                            <button type="button" className="btn btn-secondary btn-sm" title="Вставить галочку"
                                onClick={() => insertAtCursor('✔ ')}>
                                ✔
                            </button>
                            <button type="button" className="btn btn-secondary btn-sm" title="Пункт списка"
                                onClick={() => insertAtCursor('\n- ')}>
                                •&nbsp;список
                            </button>
                        </div>
                        <textarea
                            id="p-desc"
                            ref={descRef}
                            className="textarea"
                            style={{ minHeight: 140 }}
                            value={form.data.description}
                            onChange={(e) => form.setData('description', e.target.value)}
                            placeholder="Чем занимаетесь, с какого года, какие мощности и склады"
                        />
                        <p className="hint">
                            Выделите текст и нажмите «Ж» — на визитке он станет жирным. Строки, начатые с «- »,
                            превратятся в список; эмодзи ✔ ★ 📦 можно вставлять прямо в текст.
                        </p>
                    </div>

                    <button className="btn btn-primary mt-24" type="button" disabled={form.processing} onClick={submit}>
                        {company ? 'Сохранить изменения' : 'Создать компанию'}
                    </button>
                </div>
            )}

            {company && tab === 'docs' && (
                <div className="card" style={{ maxWidth: 720 }}>
                    <h3 className="t-h3">Уровень верификации</h3>
                    <p className="t-sm muted mt-8" style={{ marginBottom: 20 }}>
                        Сейчас:{' '}
                        {company.verification_level > 1 ? (
                            <span className="badge badge-gold">Проверена+</span>
                        ) : company.verification_level > 0 ? (
                            <span className="badge badge-verified">Проверена</span>
                        ) : (
                            <span className="badge badge-neutral">Не проверена</span>
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
                            На тарифе {plan?.name} заявка рассматривается за{' '}
                            <b>{pluralize(plan?.verification_days ?? 1, ['рабочий день', 'рабочих дня', 'рабочих дней'])}</b>
                            . Бейдж выдаёт модератор — купить его нельзя ни на одном тарифе.
                        </div>
                    </div>

                    <button className="btn btn-primary mt-24" onClick={() => setUploading('registration')}>
                        <Upload aria-hidden className="size-4" /> Загрузить документ
                    </button>
                </div>
            )}

            {company && tab === 'files' && (
                <div className="card" style={{ maxWidth: 820 }}>
                    <div className="row-between wrap" style={{ gap: 12, marginBottom: 6 }}>
                        <div>
                            <h3 className="t-h3">Документы и материалы</h3>
                            <p className="t-sm muted mt-8">
                                Презентации, прайс-листы, каталоги и документы. Вы сами решаете, что показать
                                на визитке партнёрам.
                            </p>
                        </div>
                        <button className="btn btn-primary" onClick={() => setUploading('presentation')}>
                            <Upload aria-hidden className="size-4" /> Загрузить файл
                        </button>
                    </div>

                    {documents.length === 0 ? (
                        <div className="empty" style={{ padding: '40px 0' }}>
                            <div className="empty-icon">
                                <FileText aria-hidden className="size-7" />
                            </div>
                            <p className="t-h4">Файлов пока нет</p>
                            <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                                Прайс-лист и презентация на визитке снимают половину первых вопросов —
                                партнёр видит ассортимент и условия до звонка.
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
                                            {d.valid_until && ` · до ${d.valid_until}`}
                                        </span>
                                    </span>

                                    {/* Документы проходят модерацию, материалы — нет:
                                        статус показываем только там, где он есть */}
                                    {!d.is_material && (
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
                                                ? 'Проверен'
                                                : d.status === 'rejected'
                                                  ? 'Отклонён'
                                                  : 'На проверке'}
                                        </span>
                                    )}

                                    <label className="check shrink-0" title="Показывать на визитке">
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
                                        <span className="hide-mobile">На визитке</span>
                                    </label>

                                    <button
                                        className="btn btn-ghost btn-icon shrink-0"
                                        aria-label={`Удалить «${d.title}»`}
                                        onClick={() =>
                                            confirm({
                                                title: `Удалить «${d.title}»?`,
                                                description: d.is_public
                                                    ? 'Файл исчезнет и с визитки — партнёры его больше не увидят.'
                                                    : 'Файл будет удалён безвозвратно.',
                                                confirmLabel: 'Удалить',
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
                        <p className="muted">
                            Конструктор мини-сайта: блоки «О компании», «Преимущества», «Продукция», «Галерея»,
                            «Документы», «Команда», «Контакты», «Карта». Появится в ближайшем обновлении.
                        </p>
                    ) : (
                        <>
                            <p className="muted">Мини-сайт доступен на тарифах Business и Premium.</p>
                            <Link href={routes.pricing} className="btn btn-outline mt-16">
                                Сравнить тарифы
                            </Link>
                        </>
                    )}
                </Panel>
            )}

            {company && tab === 'staff' && (
                <Panel
                    title="Сотрудники"
                    /* Кнопка была отключена и молчала о причине. Пояснение
                       и так есть внизу раздела — дублировать его значком
                       честнее, чем показывать мёртвую кнопку */
                    action={<span className="badge badge-neutral">приглашения скоро</span>}
                >
                    <div className="table-wrap table-cards" style={{ border: 'none' }}>
                        <table className="table" style={{ minWidth: 0 }}>
                            <thead>
                                <tr>
                                    <th>Имя</th>
                                    <th>Почта</th>
                                    <th>Роль</th>
                                </tr>
                            </thead>
                            <tbody>
                                {employees.map((e) => (
                                    <tr key={e.id}>
                                        <td data-label="Имя">
                                            <b>{e.name}</b>
                                        </td>
                                        <td data-label="Почта">
                                            {e.email}
                                            {!e.verified && <span className="badge badge-warning">не подтверждена</span>}
                                        </td>
                                        <td data-label="Роль">{e.role}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <p className="t-sm muted mt-16">
                        Лимиты тарифа считаются на компанию, кредиты — общий кошелёк всех сотрудников. Приглашение
                        по почте появится в ближайшем обновлении.
                    </p>
                </Panel>
            )}

            {company && contacts.length > 0 && tab === 'main' && (
                <Panel title="Контакты компании" className="mt-24" >
                    <ul className="stack-12">
                        {contacts.map((c) => (
                            <li key={c.id} className="row-between">
                                <span className="t-sm">
                                    <b>{c.value}</b>
                                    {c.label && <span className="muted"> · {c.label}</span>}
                                </span>
                                <span className="badge badge-neutral">{c.is_public ? 'публичный' : 'платный'}</span>
                            </li>
                        ))}
                    </ul>
                    <p className="t-sm muted mt-16">
                        Телефоны и почта показываются частично, пока покупатель не оплатит раскрытие. Сайт виден всем.
                    </p>
                </Panel>
            )}
        </CabinetLayout>
    );
}
