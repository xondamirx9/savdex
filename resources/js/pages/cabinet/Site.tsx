import { router, useForm } from '@inertiajs/react';
import { ExternalLink, ImagePlus, Monitor, Package, Pencil, Plus, Smartphone, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { FieldError } from '@/components/FieldError';
import { Panel, formatNumber } from '@/components/cabinet';
import { Modal } from '@/components/Modal';
import { useConfirm } from '@/components/useConfirm';
import { Alert } from '@/components/ui';
import { Link } from '@/components/ui/Link';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { SelectField } from '@/components/SelectField';
import { t } from '@/lib/i18n';
import { localize } from '@/lib/locale';
import { THEME_MESSAGE, type SiteTheme } from '@/pages/site/Show';
import { routes } from '@/routes';
import { unitLabel } from '@/lib/units';

/**
 * Редактор мини-сайта.
 *
 * Слева настройки, справа живой предпросмотр в iframe. Предпросмотр —
 * настоящая страница мини-сайта (site/Show) с черновым оформлением:
 * каждое изменение уходит в неё сообщением, и сервер пересчитывает
 * цвета так же, как для посетителей.
 *
 * Сохранение и публикация разделены: «Сохранить» меняет черновик,
 * посетители видят прежний вид до «Опубликовать».
 */

type Props = {
    available: boolean;
    /** Что стоит до и после поля адреса: «savdex.uz/s/» или «.savdex.site» */
    address: { prefix: string; suffix: string };
    site: {
        subdomain: string;
        url: string;
        status: 'draft' | 'published';
        published_at: string | null;
        unpublished_changes: boolean;
    } | null;
    subdomain: string;
    theme: SiteTheme;
    options: {
        templates: SiteTheme['template'][];
        modes: SiteTheme['mode'][];
        radii: SiteTheme['radius'][];
        fonts: { key: string; name: string }[];
        presets: Record<string, Omit<SiteTheme, 'template' | 'hero_image'>>;
        fonts_url: string;
    };
    /** Фон первого экрана из черновика */
    hero_url: string | null;
    products: SiteProductRow[];
    products_limit: number;
    /** Действующие объявления: на сайте они показываются сами */
    listings_count: number;
    currencies: string[];
};

type SiteProductRow = {
    id: number;
    title: string;
    description: string | null;
    price: number | null;
    currency: string;
    unit: string | null;
    image: string | null;
};

type FormData = { subdomain: string; theme: SiteTheme };

export default function Site({
    available,
    address,
    site,
    subdomain,
    theme,
    options,
    hero_url,
    products,
    products_limit,
    listings_count,
    currencies,
}: Props) {
    const form = useForm<FormData>({ subdomain, theme });
    const frame = useRef<HTMLIFrameElement>(null);
    const [device, setDevice] = useState<'desktop' | 'mobile'>('desktop');

    const current = form.data.theme;
    const published = site?.status === 'published';

    // Названия шрифтов в списке — их же начертанием
    useEffect(() => {
        if (document.getElementById('ms-font-samples')) return;

        const link = document.createElement('link');
        link.id = 'ms-font-samples';
        link.rel = 'stylesheet';
        link.href = options.fonts_url;
        document.head.appendChild(link);
    }, [options.fonts_url]);

    const sendTheme = (next: SiteTheme) =>
        frame.current?.contentWindow?.postMessage({ type: THEME_MESSAGE, theme: next }, window.location.origin);

    useEffect(() => {
        sendTheme(current);
    }, [current]);

    const setTheme = (patch: Partial<SiteTheme>) => form.setData('theme', { ...current, ...patch });

    const save = () => form.patch(routes.cabinetSite, { preserveScroll: true });

    return (
        <CabinetLayout
            title={t('cabinet.site.title')}
            heading={t('cabinet.site.title')}
            subheading={t('cabinet.site.subtitle')}
            actions={
                published && site ? (
                    <a href={site.url} target="_blank" rel="noopener" className="btn btn-outline btn-sm">
                        <ExternalLink aria-hidden className="size-4" /> {t('cabinet.site.open')}
                    </a>
                ) : undefined
            }
        >
            {!available && (
                <Alert tone="warning" className="mb-16">
                    {t('cabinet.site.plan_required')}{' '}
                    <Link href={routes.pricing} className="font-semibold underline">
                        {t('cabinet.site.compare_plans')}
                    </Link>
                </Alert>
            )}

            <div className="site-editor">
                <div className="stack-16">
                    <Panel
                        title={t('cabinet.site.address')}
                        action={
                            <span className={published ? 'badge badge-verified' : 'badge badge-neutral'}>
                                {published ? t('cabinet.site.status_published') : t('cabinet.site.status_draft')}
                            </span>
                        }
                    >
                        <label className="label" htmlFor="site-subdomain">
                            {t('cabinet.site.subdomain')}
                        </label>
                        <div className="site-address">
                            {address.prefix && <span className="muted">{address.prefix}</span>}
                            <input
                                id="site-subdomain"
                                className="input"
                                value={form.data.subdomain}
                                maxLength={40}
                                autoCapitalize="none"
                                spellCheck={false}
                                onChange={(e) =>
                                    form.setData('subdomain', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))
                                }
                            />
                            {address.suffix && <span className="muted">{address.suffix}</span>}
                        </div>
                        {form.errors.subdomain ? (
                            <p className="hint" style={{ color: 'var(--danger)' }}>
                                {form.errors.subdomain}
                            </p>
                        ) : (
                            <p className="hint">{t('cabinet.site.subdomain_hint')}</p>
                        )}
                        {site?.published_at && (
                            <p className="t-sm muted mt-8">{t('cabinet.site.published_at', { date: site.published_at })}</p>
                        )}
                    </Panel>

                    <Panel title={t('cabinet.site.template')}>
                        <div className="site-choices">
                            {options.templates.map((tpl) => (
                                <button
                                    key={tpl}
                                    type="button"
                                    className={current.template === tpl ? 'site-choice site-choice-active' : 'site-choice'}
                                    aria-pressed={current.template === tpl}
                                    onClick={() => setTheme({ template: tpl })}
                                >
                                    <b>{t(`cabinet.site.templates.${tpl}`)}</b>
                                    <small className="muted">{t(`cabinet.site.templates.${tpl}_hint`)}</small>
                                </button>
                            ))}
                        </div>
                    </Panel>

                    <Panel title={t('cabinet.site.style')}>
                        <p className="label">{t('cabinet.site.presets')}</p>
                        <div className="site-presets">
                            {Object.entries(options.presets).map(([key, preset]) => (
                                <button
                                    key={key}
                                    type="button"
                                    className="site-preset"
                                    title={t(`cabinet.site.preset_names.${key}`)}
                                    onClick={() => setTheme(preset)}
                                >
                                    <span
                                        className="site-swatch"
                                        style={{
                                            background: `linear-gradient(135deg, ${preset.primary} 0 50%, ${preset.accent} 50% 100%)`,
                                            outline: preset.mode === 'dark' ? '3px solid #0b1120' : undefined,
                                        }}
                                    />
                                    <small>{t(`cabinet.site.preset_names.${key}`)}</small>
                                </button>
                            ))}
                        </div>

                        <div className="grid grid-2 mt-16">
                            <ColorField
                                id="site-primary"
                                label={t('cabinet.site.primary')}
                                value={current.primary}
                                onChange={(primary) => setTheme({ primary })}
                                error={form.errors['theme.primary' as keyof FormData]}
                            />
                            <ColorField
                                id="site-accent"
                                label={t('cabinet.site.accent')}
                                value={current.accent}
                                onChange={(accent) => setTheme({ accent })}
                                error={form.errors['theme.accent' as keyof FormData]}
                            />
                        </div>

                        <p className="label mt-16">{t('cabinet.site.mode')}</p>
                        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                            {options.modes.map((mode) => (
                                <button
                                    key={mode}
                                    type="button"
                                    className={current.mode === mode ? 'chip chip-active' : 'chip'}
                                    aria-pressed={current.mode === mode}
                                    onClick={() => setTheme({ mode })}
                                >
                                    {t(`cabinet.site.modes.${mode}`)}
                                </button>
                            ))}
                        </div>

                        <div className="grid grid-2 mt-16">
                            <FontField
                                id="site-heading-font"
                                label={t('cabinet.site.heading_font')}
                                value={current.heading_font}
                                fonts={options.fonts}
                                onChange={(heading_font) => setTheme({ heading_font })}
                            />
                            <FontField
                                id="site-body-font"
                                label={t('cabinet.site.body_font')}
                                value={current.body_font}
                                fonts={options.fonts}
                                onChange={(body_font) => setTheme({ body_font })}
                            />
                        </div>

                        <p className="label mt-16">{t('cabinet.site.radius')}</p>
                        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                            {options.radii.map((radius) => (
                                <button
                                    key={radius}
                                    type="button"
                                    className={current.radius === radius ? 'chip chip-active' : 'chip'}
                                    aria-pressed={current.radius === radius}
                                    onClick={() => setTheme({ radius })}
                                >
                                    {t(`cabinet.site.radii.${radius}`)}
                                </button>
                            ))}
                        </div>
                    </Panel>

                    <HeroPanel
                        url={hero_url}
                        disabled={!available || !site}
                        onChange={(heroImage) =>
                            form.setData((d) => ({ ...d, theme: { ...d.theme, hero_image: heroImage } }))
                        }
                    />

                    <ProductsPanel
                        products={products}
                        limit={products_limit}
                        listingsCount={listings_count}
                        currencies={currencies}
                        disabled={!available}
                    />

                    <Panel>
                        <p className="t-sm muted" style={{ marginBottom: 12 }}>
                            {site?.unpublished_changes && published
                                ? t('cabinet.site.unpublished_changes')
                                : t('cabinet.site.content_hint')}
                        </p>
                        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
                            <button
                                type="button"
                                className="btn btn-outline"
                                disabled={!available || form.processing}
                                onClick={save}
                            >
                                {t('cabinet.site.save')}
                            </button>
                            <button
                                type="button"
                                className="btn btn-primary"
                                // Публикуется сохранённое: несохранённые правки
                                // сначала записываются, потом выходят в свет
                                disabled={!available || form.processing}
                                onClick={() =>
                                    form.patch(routes.cabinetSite, {
                                        preserveScroll: true,
                                        onSuccess: () => router.post(routes.cabinetSitePublish, {}, { preserveScroll: true }),
                                    })
                                }
                            >
                                {t('cabinet.site.publish')}
                            </button>
                            {published && (
                                <button
                                    type="button"
                                    className="btn btn-ghost"
                                    onClick={() => router.post(routes.cabinetSiteUnpublish, {}, { preserveScroll: true })}
                                >
                                    {t('cabinet.site.unpublish')}
                                </button>
                            )}
                        </div>
                    </Panel>
                </div>

                <div className="site-preview-col">
                    <div className="row-between" style={{ marginBottom: 10 }}>
                        <p className="t-sm muted">{t('cabinet.site.preview')}</p>
                        <div className="row" style={{ gap: 6 }}>
                            <button
                                type="button"
                                className={device === 'desktop' ? 'chip chip-active' : 'chip'}
                                aria-pressed={device === 'desktop'}
                                aria-label={t('cabinet.site.desktop')}
                                onClick={() => setDevice('desktop')}
                            >
                                <Monitor aria-hidden className="size-4" />
                            </button>
                            <button
                                type="button"
                                className={device === 'mobile' ? 'chip chip-active' : 'chip'}
                                aria-pressed={device === 'mobile'}
                                aria-label={t('cabinet.site.mobile')}
                                onClick={() => setDevice('mobile')}
                            >
                                <Smartphone aria-hidden className="size-4" />
                            </button>
                        </div>
                    </div>
                    <div className={device === 'mobile' ? 'site-frame site-frame-mobile' : 'site-frame'}>
                        <iframe
                            ref={frame}
                            src={localize(routes.cabinetSitePreview)}
                            title={t('cabinet.site.preview')}
                            // Правки, сделанные до загрузки фрейма, догоняют его здесь
                            onLoad={() => sendTheme(form.data.theme)}
                        />
                    </div>
                </div>
            </div>
        </CabinetLayout>
    );
}

function ColorField({
    id,
    label,
    value,
    onChange,
    error,
}: {
    id: string;
    label: string;
    value: string;
    onChange: (value: string) => void;
    error?: string;
}) {
    // Текстовое поле держит набираемое значение само: промежуточное
    // «#1a5» не цвет, и отправлять его в тему нельзя
    const [text, setText] = useState(value);

    useEffect(() => setText(value), [value]);

    return (
        <div className="field">
            <label className="label" htmlFor={id}>
                {label}
            </label>
            <div className="site-color">
                <input
                    type="color"
                    value={value}
                    aria-label={label}
                    onChange={(e) => onChange(e.target.value.toLowerCase())}
                />
                <input
                    id={id}
                    className="input"
                    value={text}
                    maxLength={7}
                    spellCheck={false}
                    onChange={(e) => {
                        const next = e.target.value.trim();
                        setText(next);

                        if (/^#[0-9a-fA-F]{6}$/.test(next)) onChange(next.toLowerCase());
                    }}
                />
            </div>
            {error && (
                <p className="hint" style={{ color: 'var(--danger)' }}>
                    {error}
                </p>
            )}
        </div>
    );
}

function FontField({
    id,
    label,
    value,
    fonts,
    onChange,
}: {
    id: string;
    label: string;
    value: string;
    fonts: { key: string; name: string }[];
    onChange: (value: string) => void;
}) {
    return (
        <div className="field">
            <label className="label" htmlFor={id}>
                {label}
            </label>
            {/* Не системный <select>: браузер рисует его сам — прямые
                углы, своя синяя подсветка, и шрифт в пунктах он
                показывает не везде. А выбирают здесь как раз шрифт,
                и увидеть его до выбора важнее всего: каждая строка
                набрана тем начертанием, которое предлагает, а рядом
                образец кириллицы — латинское название о ней молчит. */}
            <SelectField
                id={id}
                className="select-field--font"
                ariaLabel={label}
                value={value}
                onChange={onChange}
                options={fonts.map((font) => ({
                    value: font.key,
                    label: font.name,
                    font: font.name,
                    hint: 'Аа Бб 123',
                }))}
            />
        </div>
    );
}

/**
 * Фон первого экрана. Загрузка сразу пишет его в черновик, поэтому
 * нужен сохранённый сайт; на сайте фон появится после публикации.
 */
function HeroPanel({
    url,
    disabled,
    onChange,
}: {
    url: string | null;
    disabled: boolean;
    onChange: (heroImage: string | null) => void;
}) {
    const input = useRef<HTMLInputElement>(null);
    const [busy, setBusy] = useState(false);

    // Новый путь фона приходит в теме страницы после загрузки
    const sync = (page: { props: Record<string, unknown> }) =>
        onChange((page.props.theme as SiteTheme | undefined)?.hero_image ?? null);

    return (
        <Panel title={t('cabinet.site.hero')}>
            {url ? (
                <img src={url} alt="" className="site-hero-thumb" />
            ) : (
                <p className="t-sm muted">{t('cabinet.site.hero_empty')}</p>
            )}
            <input
                ref={input}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                hidden
                onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = '';

                    if (!file) return;

                    setBusy(true);
                    router.post(
                        routes.cabinetSiteHero,
                        { hero: file },
                        { forceFormData: true, preserveScroll: true, onSuccess: sync, onFinish: () => setBusy(false) },
                    );
                }}
            />
            <div className="row mt-12" style={{ gap: 10, flexWrap: 'wrap' }}>
                <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    disabled={disabled || busy}
                    onClick={() => input.current?.click()}
                >
                    <ImagePlus aria-hidden className="size-4" />
                    {url ? t('cabinet.site.hero_replace') : t('cabinet.site.hero_upload')}
                </button>
                {url && (
                    <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={busy}
                        onClick={() =>
                            router.delete(routes.cabinetSiteHero, { preserveScroll: true, onSuccess: sync })
                        }
                    >
                        <Trash2 aria-hidden className="size-4" /> {t('cabinet.site.hero_remove')}
                    </button>
                )}
            </div>
            <p className="hint">{disabled ? t('cabinet.site.hero_save_first') : t('cabinet.site.hero_hint')}</p>
            <FieldError name="hero" />
        </Panel>
    );
}

type ProductForm = {
    title: string;
    description: string;
    price: string;
    currency: string;
    unit: string;
    image: File | null;
};

/**
 * Товары сайта. Объявления компании сюда не вносятся — на сайте
 * они показываются сами; здесь то, что компания хочет показать
 * только на своей странице.
 */
function ProductsPanel({
    products,
    limit,
    listingsCount,
    currencies,
    disabled,
}: {
    products: SiteProductRow[];
    limit: number;
    listingsCount: number;
    currencies: string[];
    disabled: boolean;
}) {
    const [editing, setEditing] = useState<SiteProductRow | 'new' | null>(null);
    const { confirm, dialog } = useConfirm();
    const form = useForm<ProductForm>({ title: '', description: '', price: '', currency: 'UZS', unit: '', image: null });

    const open = (product: SiteProductRow | 'new') => {
        form.clearErrors();
        form.setData(
            product === 'new'
                ? { title: '', description: '', price: '', currency: 'UZS', unit: '', image: null }
                : {
                      title: product.title,
                      description: product.description ?? '',
                      price: product.price === null ? '' : String(product.price),
                      currency: product.currency,
                      unit: product.unit ?? '',
                      image: null,
                  },
        );
        setEditing(product);
    };

    const submit = () => {
        const url =
            editing === 'new' || editing === null
                ? routes.cabinetSiteProducts
                : routes.cabinetSiteProduct(editing.id);

        form.post(url, { forceFormData: true, preserveScroll: true, onSuccess: () => setEditing(null) });
    };

    return (
        <Panel
            title={t('cabinet.site.products')}
            action={
                <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={disabled || products.length >= limit}
                    onClick={() => open('new')}
                >
                    <Plus aria-hidden className="size-4" /> {t('cabinet.site.product_add')}
                </button>
            }
        >
            {dialog}

            <p className="t-sm muted" style={{ marginBottom: 12 }}>
                {t('cabinet.site.products_listings', { count: listingsCount })}{' '}
                <Link href={routes.cabinetListings} className="font-semibold underline">
                    {t('cabinet.site.products_listings_link')}
                </Link>
            </p>

            {products.length === 0 ? (
                <p className="t-sm muted">{t('cabinet.site.products_empty')}</p>
            ) : (
                <ul className="site-products">
                    {products.map((p) => (
                        <li key={p.id} className="site-product">
                            <span className="site-product-thumb">
                                {p.image ? <img src={p.image} alt="" /> : <Package aria-hidden className="size-5" />}
                            </span>
                            <span className="site-product-text">
                                <b>{p.title}</b>
                                <small className="muted">
                                    {p.price === null
                                        ? t('site.products.negotiable')
                                        : `${formatNumber(p.price)} ${p.currency}${p.unit ? ` / ${unitLabel(p.unit)}` : ''}`}
                                </small>
                            </span>
                            <button
                                type="button"
                                className="btn btn-ghost btn-icon"
                                aria-label={t('cabinet.site.product_edit')}
                                disabled={disabled}
                                onClick={() => open(p)}
                            >
                                <Pencil aria-hidden className="size-4" />
                            </button>
                            <button
                                type="button"
                                className="btn btn-ghost btn-icon"
                                aria-label={t('cabinet.site.product_delete')}
                                onClick={() =>
                                    confirm({
                                        title: t('cabinet.site.product_delete_title', { title: p.title }),
                                        confirmLabel: t('common.delete'),
                                        danger: true,
                                        onConfirm: () =>
                                            router.delete(routes.cabinetSiteProduct(p.id), { preserveScroll: true }),
                                    })
                                }
                            >
                                <Trash2 aria-hidden className="size-4" />
                            </button>
                        </li>
                    ))}
                </ul>
            )}

            <Modal
                open={editing !== null}
                onClose={() => setEditing(null)}
                title={editing === 'new' ? t('cabinet.site.product_add') : t('cabinet.site.product_edit')}
                width={520}
                footer={
                    <div className="row" style={{ gap: 10, justifyContent: 'flex-end' }}>
                        <button type="button" className="btn btn-ghost" onClick={() => setEditing(null)}>
                            {t('common.cancel')}
                        </button>
                        <button type="button" className="btn btn-primary" disabled={form.processing} onClick={submit}>
                            {t('cabinet.site.product_save')}
                        </button>
                    </div>
                }
            >
                <div className="field">
                    <label className="label" htmlFor="sp-title">
                        {t('cabinet.site.product_title')}
                    </label>
                    <input
                        id="sp-title"
                        className="input"
                        maxLength={190}
                        value={form.data.title}
                        onChange={(e) => form.setData('title', e.target.value)}
                    />
                    {form.errors.title && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.title}</p>}
                </div>
                <div className="grid grid-2">
                    <div className="field">
                        <label className="label" htmlFor="sp-price">
                            {t('cabinet.site.product_price')}
                        </label>
                        <input
                            id="sp-price"
                            className="input"
                            inputMode="decimal"
                            value={form.data.price}
                            placeholder={t('site.products.negotiable')}
                            onChange={(e) => form.setData('price', e.target.value.replace(/[^\d.]/g, ''))}
                        />
                        {form.errors.price && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.price}</p>}
                    </div>
                    <div className="grid grid-2" style={{ gap: 8 }}>
                        <div className="field">
                            <label className="label" htmlFor="sp-currency">
                                {t('cabinet.site.product_currency')}
                            </label>
                            <select
                                id="sp-currency"
                                className="input"
                                value={form.data.currency}
                                onChange={(e) => form.setData('currency', e.target.value)}
                            >
                                {currencies.map((c) => (
                                    <option key={c} value={c}>
                                        {c}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="field">
                            <label className="label" htmlFor="sp-unit">
                                {t('cabinet.site.product_unit')}
                            </label>
                            <input
                                id="sp-unit"
                                className="input"
                                maxLength={30}
                                value={form.data.unit}
                                onChange={(e) => form.setData('unit', e.target.value)}
                            />
                        </div>
                    </div>
                </div>
                <div className="field">
                    <label className="label" htmlFor="sp-description">
                        {t('cabinet.site.product_description')}
                    </label>
                    <textarea
                        id="sp-description"
                        className="input"
                        rows={3}
                        maxLength={2000}
                        value={form.data.description}
                        onChange={(e) => form.setData('description', e.target.value)}
                    />
                </div>
                <div className="field">
                    <label className="label" htmlFor="sp-image">
                        {t('cabinet.site.product_photo')}
                    </label>
                    <input
                        id="sp-image"
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        onChange={(e) => form.setData('image', e.target.files?.[0] ?? null)}
                    />
                    {form.errors.image && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.image}</p>}
                </div>
            </Modal>
        </Panel>
    );
}
