import { router, useForm } from '@inertiajs/react';
import { Check, CloudUpload, Package, ShoppingCart, TriangleAlert } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { PhotoUploader, type ListingPhoto } from '@/components/PhotoUploader';
import { SelectField } from '@/components/SelectField';
import { useConfirm } from '@/components/useConfirm';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';

interface Field {
    key: string;
    label: string;
    type: string;
    options: string[];
    unit: string | null;
}

interface Child {
    id: number;
    name: string;
    fields: Field[];
}

interface Parent {
    id: number;
    slug: string;
    name: string;
    children: Child[];
}

interface Props {
    listing: {
        id: number;
        type: 'supply' | 'demand';
        category_id: number | null;
        parent_id: number | null;
        title: string;
        description: string | null;
        price: number | null;
        bundle_price: number | null;
        currency: string;
        unit: string | null;
        price_negotiable: boolean;
        min_order: number | null;
        delivery_terms: string | null;
        payment_terms: string | null;
        status: string;
        step: number;
        tags: string[];
        attributes: Record<string, string>;
        images: ListingPhoto[];
    };
    categories: Parent[];
    slots: { used: number; total: number | null };
    /** Из чего владелец выбирает теги — своих он не пишет */
    tagOptions: string[];
}

/* Ключи, а не подписи: шаги рисуются на языке сайта */
const STEPS = ['category', 'price', 'terms', 'photos'];

/**
 * На каком шаге искать поле, которое не прошло проверку.
 *
 * Публикация проверяется целиком, а нажимают её на последнем шаге —
 * без этой карты человек видел бы «не опубликовалось» и не знал,
 * где именно править.
 */
const FIELD_STEP: Record<string, number> = {
    type: 1,
    category_id: 1,
    title: 1,
    description: 2,
    price: 2,
    currency: 2,
};

const TIPS = ['brand', 'photos', 'quality', 'price'];

export default function Wizard({ listing, categories, slots, tagOptions }: Props) {
    const [step, setStep] = useState(listing.step);
    const [savedAgo, setSavedAgo] = useState<string | null>(null);
    // Список вариантов обновляется с каждым автосохранением:
    // заголовок поменялся — предложения пересобрались
    const [tagChoices, setTagChoices] = useState<string[]>(tagOptions);
    const { confirm, dialog } = useConfirm();

    const { data, setData, errors, processing, post } = useForm({
        type: listing.type,
        parent_id: listing.parent_id,
        category_id: listing.category_id,
        title: listing.title,
        description: listing.description ?? '',
        price: listing.price,
        bundle_price: listing.bundle_price,
        currency: listing.currency,
        unit: listing.unit ?? '',
        price_negotiable: listing.price_negotiable,
        min_order: listing.min_order,
        delivery_terms: listing.delivery_terms ?? '',
        payment_terms: listing.payment_terms ?? '',
        tags: listing.tags ?? [],
        attributes: listing.attributes ?? {},
    });

    const parent = categories.find((c) => c.id === data.parent_id);
    const child = parent?.children.find((c) => c.id === data.category_id);

    /*
     * Раздел «Другое» устроен иначе: подкатегория в нём одна («Разные
     * товары») и выбирать её бессмысленно — селект прячется, рубрика
     * проставляется сама, а вместо неё продавец пишет свою категорию
     * текстом. Хранится она как атрибут custom_category — тем же
     * механизмом, что и поля обычных категорий.
     */
    const isOther = parent?.slug === 'drugoe';

    /*
     * Автосохранение раз в 20 секунд, как обещано в интерфейсе.
     * Отдельный fetch, а не router.post: перезагрузка страницы посреди
     * набора текста сбрасывала бы курсор и позицию прокрутки.
     */
    const payload = useRef(data);
    payload.current = data;

    const save = useCallback(async () => {
        const token = document.cookie.match(/XSRF-TOKEN=([^;]+)/)?.[1];

        const res = await fetch(`/cabinet/listings/${listing.id}/autosave`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                ...(token ? { 'X-XSRF-TOKEN': decodeURIComponent(token) } : {}),
            },
            body: JSON.stringify({ ...payload.current, step }),
        });

        if (res.ok) {
            setSavedAgo(new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }));

            const body = (await res.json()) as { tag_options?: string[] };
            if (body.tag_options) setTagChoices(body.tag_options);
        }
    }, [listing.id, step]);

    useEffect(() => {
        const id = setInterval(save, 20_000);
        return () => clearInterval(id);
    }, [save]);

    function go(next: number) {
        void save();
        setStep(next);
        window.scrollTo({ top: 0, behavior: 'instant' });
    }

    function publish() {
        post(`/cabinet/listings/${listing.id}/publish`, { preserveScroll: true });
    }

    /*
     * Ошибки публикации в порядке шагов. Отклонённое объявление
     * возвращается на этот же экран, и без списка причин человек
     * жмёт «Опубликовать» повторно, ничего не исправив.
     */
    const problems = Object.entries(errors)
        .map(([field, message]) => ({ field, message: String(message), step: FIELD_STEP[field] ?? 1 }))
        .sort((a, b) => a.step - b.step);

    const titleLeft = 90 - data.title.length;
    const descLeft = 5000 - data.description.length;

    return (
        <CabinetLayout
            title={t('cabinet.wizard.title')}
            heading={listing.status === 'draft' ? t('cabinet.wizard.title') : t('cabinet.wizard.editing')}
            subheading={t('cabinet.wizard.autosave')}
            /* Кнопка остаётся на месте после автосохранения: раньше она
               подменялась отметкой времени, и сохранить черновик руками
               становилось нечем — а именно этого от неё и ждут */
            actions={
                <div className="row" style={{ gap: 10, alignItems: 'center' }}>
                    {savedAgo && (
                        <span className="badge badge-neutral">
                            <Check aria-hidden className="size-3.5" />{' '}
                            {t('cabinet.wizard.saved_at', { time: savedAgo })}
                        </span>
                    )}
                    <button className="btn btn-secondary btn-sm" onClick={() => void save()}>
                        <CloudUpload aria-hidden className="size-4" /> {t('cabinet.wizard.save_draft')}
                    </button>
                </div>
            }
        >
            {dialog}

            <div className="steps">
                {STEPS.map((key, i) => (
                    <span key={key} style={{ display: 'contents' }}>
                        {i > 0 && <span className="step-line" />}
                        <button
                            type="button"
                            className={cn('step', i + 1 === step && 'is-active', i + 1 < step && 'is-done')}
                            onClick={() => go(i + 1)}
                        >
                            <span className="step-dot">{i + 1 < step ? <Check aria-hidden className="size-3.5" /> : i + 1}</span>
                            <span className="hide-mobile">{t(`cabinet.wizard.step_${key}`)}</span>
                        </button>
                    </span>
                ))}
            </div>

            <div className="grid grid-sidebar" style={{ ['--aside' as string]: '320px', gap: 24, alignItems: 'start' }}>
                <div className="card">
                    {step === 1 && (
                        <>
                            <fieldset style={{ border: 'none' }}>
                                <legend className="t-h3" style={{ marginBottom: 16 }}>
                                    {t('cabinet.wizard.what')}
                                </legend>
                                <div className="radio-cards grid-2">
                                    {(
                                        [
                                            ['supply', Package],
                                            ['demand', ShoppingCart],
                                        ] as const
                                    ).map(([value, Icon]) => (
                                        <label key={value} className="radio-card">
                                            <input
                                                type="radio"
                                                name="type"
                                                checked={data.type === value}
                                                onChange={() => setData('type', value)}
                                            />
                                            <div className="radio-card-body">
                                                <div className="radio-card-title row" style={{ gap: 8 }}>
                                                    <Icon aria-hidden className="size-4" />{' '}
                                                    {t(`cabinet.wizard.type_${value}`)}
                                                </div>
                                                <div className="radio-card-desc">
                                                    {t(`cabinet.wizard.type_${value}_desc`)}
                                                </div>
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            </fieldset>

                            <div className="field mt-24">
                                <label className="label" htmlFor="w-cat">
                                    {t('cabinet.wizard.category')} <span className="req">*</span>
                                </label>
                                <SelectField
                                    id="w-cat"
                                    ariaLabel={t('cabinet.wizard.category')}
                                    value={String(data.parent_id ?? '')}
                                    onChange={(value) => {
                                        const next = categories.find((c) => c.id === Number(value));
                                        setData('parent_id', next?.id ?? null);
                                        setData('category_id', next?.slug === 'drugoe' ? (next.children[0]?.id ?? null) : null);
                                    }}
                                    placeholder={t('cabinet.wizard.pick_category')}
                                    options={categories.map((c) => ({ value: String(c.id), label: c.name }))}
                                />
                            </div>

                            {parent && isOther && (
                                <div className="field">
                                    <label className="label" htmlFor="w-custom-cat">
                                        {t('cabinet.wizard.own_category')} <span className="req">*</span>
                                    </label>
                                    <input
                                        id="w-custom-cat"
                                        className="input"
                                        maxLength={80}
                                        value={data.attributes.custom_category ?? ''}
                                        onChange={(e) =>
                                            setData('attributes', { ...data.attributes, custom_category: e.target.value })
                                        }
                                        placeholder={t('cabinet.wizard.own_category_placeholder')}
                                    />
                                    <p className="hint">{t('cabinet.wizard.own_category_hint')}</p>
                                </div>
                            )}

                            {parent && !isOther && (
                                <div className="field">
                                    <label className="label" htmlFor="w-sub">
                                        {t('cabinet.wizard.subcategory')} <span className="req">*</span>
                                    </label>
                                    <SelectField
                                        id="w-sub"
                                        ariaLabel={t('cabinet.wizard.subcategory')}
                                        value={String(data.category_id ?? '')}
                                        onChange={(value) => setData('category_id', value ? Number(value) : null)}
                                        placeholder={t('cabinet.wizard.pick_subcategory')}
                                        options={parent.children.map((c) => ({ value: String(c.id), label: c.name }))}
                                    />
                                    {errors.category_id && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.category_id}</p>}
                                </div>
                            )}

                            <div className="field">
                                <label className="label" htmlFor="w-title">
                                    {t('cabinet.wizard.heading')} <span className="req">*</span>
                                </label>
                                <input
                                    id="w-title"
                                    className="input"
                                    maxLength={90}
                                    value={data.title}
                                    onChange={(e) => setData('title', e.target.value)}
                                    placeholder={t('cabinet.wizard.heading_placeholder')}
                                />
                                <p className="hint">
                                    {t('cabinet.wizard.chars', { used: data.title.length, max: 90 })}
                                    {titleLeft < 15 && ` · ${t('cabinet.wizard.chars_left', { left: titleLeft })}`}.{' '}
                                    {t('cabinet.wizard.heading_hint')}
                                </p>
                                {errors.title && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.title}</p>}
                            </div>

                            {/* Поля категории появляются только после её выбора:
                                показывать пустой блок «поля появятся позже» — шум */}
                            {!isOther && child && child.fields.length > 0 && (
                                <div
                                    className="card card--pad-sm mt-24"
                                    style={{ background: 'var(--primary-50)', borderColor: 'var(--primary-100)' }}
                                >
                                    <p className="t-caption muted" style={{ marginBottom: 12 }}>
                                        {t('cabinet.wizard.category_fields', { category: child.name })}
                                    </p>
                                    <div className="grid grid-2 grid-tight" style={{ gap: 12 }}>
                                        {child.fields.map((f) => (
                                            <div key={f.key} className="field" style={{ margin: 0 }}>
                                                <label className="label" htmlFor={`w-${f.key}`}>
                                                    {f.label}
                                                </label>
                                                {f.type === 'select' ? (
                                                    <SelectField
                                                        id={`w-${f.key}`}
                                                        ariaLabel={f.label}
                                                        value={data.attributes[f.key] ?? ''}
                                                        onChange={(value) =>
                                                            setData('attributes', { ...data.attributes, [f.key]: value })
                                                        }
                                                        placeholder={t('cabinet.wizard.not_set')}
                                                        options={f.options.map((o) => ({ value: o, label: o }))}
                                                    />
                                                ) : (
                                                    <input
                                                        id={`w-${f.key}`}
                                                        className="input"
                                                        type={f.type === 'number' ? 'number' : 'text'}
                                                        value={data.attributes[f.key] ?? ''}
                                                        onChange={(e) =>
                                                            setData('attributes', { ...data.attributes, [f.key]: e.target.value })
                                                        }
                                                    />
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            <div className="row mt-32" style={{ gap: 10 }}>
                                <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => go(2)}>
                                    {t('cabinet.wizard.next_price')}
                                </button>
                            </div>
                        </>
                    )}

                    {step === 2 && (
                        <>
                            <h2 className="t-h3" style={{ marginBottom: 16 }}>
                                {t('cabinet.wizard.step_price_title')}
                            </h2>

                            <div className="field">
                                <label className="label" htmlFor="w-desc">
                                    {t('cabinet.wizard.description')} <span className="req">*</span>
                                </label>
                                <textarea
                                    id="w-desc"
                                    className="textarea"
                                    maxLength={5000}
                                    value={data.description}
                                    onChange={(e) => setData('description', e.target.value)}
                                    placeholder={t('cabinet.wizard.description_placeholder')}
                                />
                                <p className="hint">
                                    {t('cabinet.wizard.chars', { used: data.description.length, max: 5000 })}
                                    {descLeft < 200 && ` · ${t('cabinet.wizard.chars_left', { left: descLeft })}`}.{' '}
                                    {t('cabinet.wizard.description_hint')}
                                </p>
                                {errors.description && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.description}</p>}
                            </div>

                            <div className="grid grid-2 grid-tight mt-24" style={{ gap: 12 }}>
                                <div className="field" style={{ margin: 0 }}>
                                    <label className="label" htmlFor="w-price">
                                        {t('cabinet.wizard.price')}
                                    </label>
                                    <input
                                        id="w-price"
                                        className="input"
                                        type="number"
                                        min={0}
                                        disabled={data.price_negotiable}
                                        value={data.price ?? ''}
                                        onChange={(e) => setData('price', e.target.value ? Number(e.target.value) : null)}
                                        placeholder="1200000"
                                    />
                                </div>
                                <div className="field" style={{ margin: 0 }}>
                                    <label className="label" htmlFor="w-cur">
                                        {t('cabinet.wizard.currency')}
                                    </label>
                                    <SelectField
                                        id="w-cur"
                                        ariaLabel={t('cabinet.wizard.currency')}
                                        value={data.currency}
                                        onChange={(value) => setData('currency', value)}
                                        options={[
                                            { value: 'UZS', label: t('cabinet.wizard.uzs') },
                                            { value: 'USD', label: t('cabinet.wizard.usd') },
                                        ]}
                                    />
                                </div>
                            </div>

                            {/* Комплект: товар нередко продаётся набором, и цена
                                единицы не отвечает, сколько стоит весь набор */}
                            <div className="field mt-12" style={{ margin: 0 }}>
                                <label className="label" htmlFor="w-bundle">
                                    {t('cabinet.wizard.bundle')}{' '}
                                    <span className="muted">{t('cabinet.wizard.optional')}</span>
                                </label>
                                <input
                                    id="w-bundle"
                                    className="input"
                                    type="number"
                                    min={0}
                                    disabled={data.price_negotiable}
                                    value={data.bundle_price ?? ''}
                                    onChange={(e) => setData('bundle_price', e.target.value ? Number(e.target.value) : null)}
                                    placeholder="6000000"
                                />
                                <p className="hint">{t('cabinet.wizard.bundle_hint')}</p>
                            </div>

                            <div className="grid grid-2 grid-tight mt-12" style={{ gap: 12 }}>
                                <div className="field" style={{ margin: 0 }}>
                                    <label className="label" htmlFor="w-unit">
                                        {t('cabinet.wizard.unit')}
                                    </label>
                                    <input
                                        id="w-unit"
                                        className="input"
                                        value={data.unit}
                                        onChange={(e) => setData('unit', e.target.value)}
                                        placeholder={t('cabinet.wizard.unit_placeholder')}
                                    />
                                </div>
                                <div className="field" style={{ margin: 0 }}>
                                    <label className="label" htmlFor="w-min">
                                        {t('cabinet.wizard.min_order')}
                                    </label>
                                    <input
                                        id="w-min"
                                        className="input"
                                        type="number"
                                        min={0}
                                        value={data.min_order ?? ''}
                                        onChange={(e) => setData('min_order', e.target.value ? Number(e.target.value) : null)}
                                    />
                                </div>
                            </div>

                            <label className="check mt-12">
                                <input
                                    type="checkbox"
                                    checked={data.price_negotiable}
                                    onChange={(e) => setData('price_negotiable', e.target.checked)}
                                />
                                {t('cabinet.wizard.negotiable')}
                            </label>
                            {errors.price && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.price}</p>}

                            <div className="row mt-32" style={{ gap: 10 }}>
                                <button className="btn btn-secondary" onClick={() => go(1)}>
                                    {t('cabinet.wizard.back')}
                                </button>
                                <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => go(3)}>
                                    {t('cabinet.wizard.next_terms')}
                                </button>
                            </div>
                        </>
                    )}

                    {step === 3 && (
                        <>
                            <h2 className="t-h3" style={{ marginBottom: 16 }}>
                                {t('cabinet.wizard.step_terms_title')}
                            </h2>

                            <div className="field">
                                <label className="label" htmlFor="w-delivery">
                                    {t('cabinet.wizard.delivery')}
                                </label>
                                <textarea
                                    id="w-delivery"
                                    className="textarea"
                                    style={{ minHeight: 90 }}
                                    value={data.delivery_terms}
                                    onChange={(e) => setData('delivery_terms', e.target.value)}
                                    placeholder={t('cabinet.wizard.delivery_placeholder')}
                                />
                            </div>

                            <div className="field">
                                <label className="label" htmlFor="w-payment">
                                    {t('cabinet.wizard.payment')}
                                </label>
                                <textarea
                                    id="w-payment"
                                    className="textarea"
                                    style={{ minHeight: 90 }}
                                    value={data.payment_terms}
                                    onChange={(e) => setData('payment_terms', e.target.value)}
                                    placeholder={t('cabinet.wizard.payment_placeholder')}
                                />
                            </div>

                            <div className="row mt-32" style={{ gap: 10 }}>
                                <button className="btn btn-secondary" onClick={() => go(2)}>
                                    {t('cabinet.wizard.back')}
                                </button>
                                <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => go(4)}>
                                    {t('cabinet.wizard.next_photos')}
                                </button>
                            </div>
                        </>
                    )}

                    {step === 4 && (
                        <>
                            <h2 className="t-h3" style={{ marginBottom: 16 }}>
                                {t('cabinet.wizard.step_photos')}
                            </h2>

                            <PhotoUploader listingId={listing.id} photos={listing.images} />

                            {/* Теги — только выбор из предложенного: свои слова
                                писать нельзя, сервер их всё равно отбросит.
                                Список собирается из заголовка, категории
                                и характеристик и обновляется автосохранением */}
                            {tagChoices.length > 0 && (
                                <div className="mt-24">
                                    <p className="label" style={{ marginBottom: 4 }}>
                                        {t('cabinet.wizard.tags')}
                                    </p>
                                    <p className="t-caption muted" style={{ marginBottom: 10 }}>
                                        {t('cabinet.wizard.tags_hint')}
                                    </p>
                                    <div className="row wrap" style={{ gap: 8 }}>
                                        {tagChoices.map((tag) => {
                                            const active = data.tags.includes(tag);

                                            return (
                                                <button
                                                    key={tag}
                                                    type="button"
                                                    className={cn('tag-pick', active && 'tag-pick--on')}
                                                    aria-pressed={active}
                                                    onClick={() =>
                                                        setData(
                                                            'tags',
                                                            active
                                                                ? data.tags.filter((x) => x !== tag)
                                                                : data.tags.length < 8
                                                                  ? [...data.tags, tag]
                                                                  : data.tags,
                                                        )
                                                    }
                                                >
                                                    #{tag.replace(/\s+/g, '')}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}

                            {problems.length > 0 ? (
                                <div className="alert alert-danger mt-24">
                                    <TriangleAlert aria-hidden className="size-5" />
                                    <div>
                                        <b>{t('cabinet.wizard.not_published')}</b>
                                        <ul className="stack-8 mt-8">
                                            {problems.map((p) => (
                                                <li key={p.field}>
                                                    {p.message}{' '}
                                                    <button
                                                        type="button"
                                                        className="link"
                                                        onClick={() => go(p.step)}
                                                    >
                                                        {t('cabinet.wizard.go_step', {
                                                            step: p.step,
                                                            name: t(`cabinet.wizard.step_${STEPS[p.step - 1]}`),
                                                        })}
                                                    </button>
                                                </li>
                                            ))}
                                        </ul>
                                        <p className="t-sm mt-8">{t('cabinet.wizard.draft_kept')}</p>
                                    </div>
                                </div>
                            ) : (
                                <div className="alert alert-info mt-24">
                                    <Check aria-hidden className="size-5" />
                                    <div>{t('cabinet.wizard.will_appear')}</div>
                                </div>
                            )}

                            <div className="row mt-32" style={{ gap: 10 }}>
                                <button className="btn btn-secondary" onClick={() => go(3)}>
                                    {t('cabinet.wizard.back')}
                                </button>
                                <button className="btn btn-primary" style={{ flex: 1 }} disabled={processing} onClick={publish}>
                                    {processing ? t('cabinet.wizard.sending') : t('cabinet.wizard.publish')}
                                </button>
                            </div>
                        </>
                    )}
                </div>

                <aside className="stack-16">
                    <div className="card">
                        <h3 className="t-h4" style={{ marginBottom: 12 }}>
                            {t('cabinet.wizard.tips')}
                        </h3>
                        <ul className="stack-12 t-sm">
                            {TIPS.map((tip) => (
                                <li key={tip} className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                                    <Check aria-hidden className="size-4 shrink-0" style={{ color: 'var(--success)', marginTop: 4 }} />
                                    {t(`cabinet.wizard.tip_${tip}`)}
                                </li>
                            ))}
                        </ul>
                    </div>

                    <div className="card" style={{ background: 'var(--primary-50)', borderColor: 'var(--primary-100)' }}>
                        <p className="t-sm">
                            <b>{t('cabinet.wizard.slots')}</b>{' '}
                            {slots.total === null
                                ? t('cabinet.common.unlimited')
                                : t('cabinet.wizard.slots_left', {
                                      left: slots.total - slots.used,
                                      total: slots.total,
                                  })}
                        </p>
                        <p className="t-sm muted mt-8">{t('cabinet.wizard.slots_hint')}</p>
                    </div>

                    <button
                        className="btn btn-ghost btn-block"
                        onClick={() =>
                            confirm({
                                title: t('cabinet.wizard.delete_title'),
                                description: t('cabinet.wizard.delete_text'),
                                confirmLabel: t('cabinet.wizard.delete'),
                                danger: true,
                                onConfirm: () => router.delete(`/cabinet/listings/${listing.id}`),
                            })
                        }
                    >
                        {t('cabinet.wizard.delete')}
                    </button>
                </aside>
            </div>
        </CabinetLayout>
    );
}
