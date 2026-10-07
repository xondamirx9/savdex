import { useForm } from '@inertiajs/react';
import { ArrowLeft } from 'lucide-react';
import { SelectField } from '@/components/SelectField';
import { Link } from '@/components/ui/Link';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

interface Fields {
    title: string;
    description: string;
    customer: string;
    category_id: string;
    location: string;
    budget: string;
    currency: string;
    deadline_at: string;
    contact_name: string;
    contact_phone: string;
    contact_email: string;
}

interface Props {
    tender: (Fields & { id: number }) | null;
    /** Подстановка в новую форму: заказчик — компания, контакт — вошедший */
    defaults: Pick<Fields, 'customer' | 'contact_name' | 'contact_phone' | 'contact_email'> | null;
    categories: { value: string; label: string }[];
    currencies: string[];
}

/** Новый тендер и правка своего — одна форма, как у IT-задачи */
export default function TenderForm({ tender, defaults, categories, currencies }: Props) {
    const form = useForm<Fields>({
        title: tender?.title ?? '',
        description: tender?.description ?? '',
        customer: tender?.customer ?? defaults?.customer ?? '',
        category_id: tender?.category_id ?? '',
        location: tender?.location ?? '',
        budget: tender?.budget ?? '',
        currency: tender?.currency ?? 'UZS',
        deadline_at: tender?.deadline_at ?? '',
        contact_name: tender?.contact_name ?? defaults?.contact_name ?? '',
        contact_phone: tender?.contact_phone ?? defaults?.contact_phone ?? '',
        contact_email: tender?.contact_email ?? defaults?.contact_email ?? '',
    });

    function submit(e: React.FormEvent) {
        e.preventDefault();

        if (tender) {
            form.patch(routes.tenderUpdate(tender.id), { preserveScroll: true });
        } else {
            form.post(routes.cabinetTenders, { preserveScroll: true });
        }
    }

    const error = (key: keyof Fields) =>
        form.errors[key] ? (
            <p className="hint" style={{ color: 'var(--danger)' }}>
                {form.errors[key]}
            </p>
        ) : null;

    const text = (key: keyof Fields, label: string, options: { placeholder?: string; type?: string; max?: number; required?: boolean } = {}) => (
        <div className="field">
            <label className="label" htmlFor={`tn-${key}`}>
                {label} {options.required && <span className="req">*</span>}
            </label>
            <input
                id={`tn-${key}`}
                className="input"
                type={options.type ?? 'text'}
                value={form.data[key]}
                onChange={(e) => form.setData(key, e.target.value)}
                placeholder={options.placeholder}
                maxLength={options.max}
            />
            {error(key)}
        </div>
    );

    const heading = tender ? t('cabinet.tender_form.edit') : t('cabinet.tender_form.create');

    return (
        <CabinetLayout
            title={heading}
            heading={heading}
            subheading={t('cabinet.tender_form.subtitle')}
            actions={
                <Link href={routes.cabinetTenders} className="btn btn-secondary btn-sm">
                    <ArrowLeft aria-hidden className="size-4" /> {t('cabinet.tender_form.all')}
                </Link>
            }
        >
            <form onSubmit={submit} className="card" style={{ maxWidth: 760 }}>
                {text('title', t('cabinet.tender_form.name'), {
                    placeholder: t('cabinet.tender_form.name_placeholder'),
                    max: 190,
                    required: true,
                })}

                <div className="field">
                    <label className="label" htmlFor="tn-description">
                        {t('cabinet.tender_form.description')} <span className="req">*</span>
                    </label>
                    <textarea
                        id="tn-description"
                        className="input"
                        rows={8}
                        maxLength={8000}
                        value={form.data.description}
                        onChange={(e) => form.setData('description', e.target.value)}
                        placeholder={t('cabinet.tender_form.description_placeholder')}
                    />
                    {error('description')}
                </div>

                {text('customer', t('cabinet.tender_form.customer'), { max: 190, required: true })}

                <div className="field">
                    <label className="label" htmlFor="tn-category">
                        {t('cabinet.tender_form.category')}
                    </label>
                    <SelectField
                        id="tn-category"
                        ariaLabel={t('cabinet.tender_form.category')}
                        value={form.data.category_id}
                        onChange={(value) => form.setData('category_id', value)}
                        placeholder={t('cabinet.tender_form.category_none')}
                        options={categories}
                    />
                    {error('category_id')}
                </div>

                {text('location', t('cabinet.tender_form.location'), {
                    placeholder: t('cabinet.tender_form.location_placeholder'),
                    max: 190,
                })}

                <div className="field">
                    <label className="label" htmlFor="tn-budget">
                        {t('cabinet.tender_form.budget')}
                    </label>
                    <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                        <input
                            id="tn-budget"
                            className="input"
                            type="number"
                            min={0}
                            inputMode="numeric"
                            style={{ flex: 1, minWidth: 0 }}
                            value={form.data.budget}
                            onChange={(e) => form.setData('budget', e.target.value)}
                            placeholder={t('cabinet.tender_form.budget_placeholder')}
                        />
                        <SelectField
                            className="select-field--auto"
                            ariaLabel={t('cabinet.tender_form.currency')}
                            value={form.data.currency}
                            onChange={(value) => form.setData('currency', value)}
                            options={currencies.map((c) => ({ value: c, label: c === 'UZS' ? t('catalog.currency_uzs') : c }))}
                        />
                    </div>
                    {error('budget')}
                    {error('currency')}
                </div>

                <div className="field">
                    <label className="label" htmlFor="tn-deadline_at">
                        {t('cabinet.tender_form.deadline')}
                    </label>
                    <input
                        id="tn-deadline_at"
                        className="input"
                        type="date"
                        style={{ maxWidth: 220 }}
                        value={form.data.deadline_at}
                        onChange={(e) => form.setData('deadline_at', e.target.value)}
                    />
                    {error('deadline_at')}
                </div>

                <h3 className="t-h4" style={{ margin: '24px 0 12px' }}>
                    {t('cabinet.tender_form.contacts')}
                </h3>
                {text('contact_name', t('cabinet.tender_form.contact_name'), { max: 190 })}
                {text('contact_phone', t('cabinet.tender_form.contact_phone'), { type: 'tel', max: 40 })}
                {text('contact_email', t('cabinet.tender_form.contact_email'), { type: 'email', max: 190 })}

                <div className="row" style={{ gap: 10, marginTop: 24 }}>
                    <button className="btn btn-primary" type="submit" disabled={form.processing}>
                        {tender ? t('common.save') : t('cabinet.tender_form.publish')}
                    </button>
                </div>
                {!tender && <p className="hint mt-12">{t('cabinet.tender_form.after_publish')}</p>}
            </form>
        </CabinetLayout>
    );
}
