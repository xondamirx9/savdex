import { router, useForm } from '@inertiajs/react';
import { Check, CloudUpload, Package, ShoppingCart, TriangleAlert } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { PhotoUploader, type ListingPhoto } from '@/components/PhotoUploader';
import { useConfirm } from '@/components/useConfirm';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';

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
        currency: string;
        unit: string | null;
        price_negotiable: boolean;
        min_order: number | null;
        delivery_terms: string | null;
        payment_terms: string | null;
        status: string;
        step: number;
        attributes: Record<string, string>;
        images: ListingPhoto[];
    };
    categories: Parent[];
    slots: { used: number; total: number | null };
}

const STEPS = ['Тип и категория', 'Товар и цена', 'Условия', 'Фото и документы'];

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

const TIPS = [
    'Укажите точную марку и объём — по ним ищут',
    'Добавьте минимум 3 фото товара',
    'Приложите паспорт качества — доверие выше',
    'Не скрывайте цену: объявления с ценой смотрят в 2,4 раза чаще',
];

export default function Wizard({ listing, categories, slots }: Props) {
    const [step, setStep] = useState(listing.step);
    const [savedAgo, setSavedAgo] = useState<string | null>(null);
    const { confirm, dialog } = useConfirm();

    const { data, setData, errors, processing, post } = useForm({
        type: listing.type,
        parent_id: listing.parent_id,
        category_id: listing.category_id,
        title: listing.title,
        description: listing.description ?? '',
        price: listing.price,
        currency: listing.currency,
        unit: listing.unit ?? '',
        price_negotiable: listing.price_negotiable,
        min_order: listing.min_order,
        delivery_terms: listing.delivery_terms ?? '',
        payment_terms: listing.payment_terms ?? '',
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

        if (res.ok) setSavedAgo(new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }));
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
            title="Новое объявление"
            heading={listing.status === 'draft' ? 'Новое объявление' : 'Редактирование'}
            subheading="Черновик сохраняется автоматически каждые 20 секунд"
            /* Кнопка остаётся на месте после автосохранения: раньше она
               подменялась отметкой времени, и сохранить черновик руками
               становилось нечем — а именно этого от неё и ждут */
            actions={
                <div className="row" style={{ gap: 10, alignItems: 'center' }}>
                    {savedAgo && (
                        <span className="badge badge-neutral">
                            <Check aria-hidden className="size-3.5" /> Сохранено в {savedAgo}
                        </span>
                    )}
                    <button className="btn btn-secondary btn-sm" onClick={() => void save()}>
                        <CloudUpload aria-hidden className="size-4" /> Сохранить черновик
                    </button>
                </div>
            }
        >
            {dialog}

            <div className="steps">
                {STEPS.map((label, i) => (
                    <span key={label} style={{ display: 'contents' }}>
                        {i > 0 && <span className="step-line" />}
                        <button
                            type="button"
                            className={cn('step', i + 1 === step && 'is-active', i + 1 < step && 'is-done')}
                            onClick={() => go(i + 1)}
                        >
                            <span className="step-dot">{i + 1 < step ? <Check aria-hidden className="size-3.5" /> : i + 1}</span>
                            <span className="hide-mobile">{label}</span>
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
                                    Что вы публикуете?
                                </legend>
                                <div className="radio-cards grid-2">
                                    {(
                                        [
                                            ['supply', 'Предложение', 'У меня есть товар', Package],
                                            ['demand', 'Запрос', 'Мне нужен товар', ShoppingCart],
                                        ] as const
                                    ).map(([value, title, desc, Icon]) => (
                                        <label key={value} className="radio-card">
                                            <input
                                                type="radio"
                                                name="type"
                                                checked={data.type === value}
                                                onChange={() => setData('type', value)}
                                            />
                                            <div className="radio-card-body">
                                                <div className="radio-card-title row" style={{ gap: 8 }}>
                                                    <Icon aria-hidden className="size-4" /> {title}
                                                </div>
                                                <div className="radio-card-desc">{desc}</div>
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            </fieldset>

                            <div className="field mt-24">
                                <label className="label" htmlFor="w-cat">
                                    Категория <span className="req">*</span>
                                </label>
                                <select
                                    id="w-cat"
                                    className="select"
                                    value={data.parent_id ?? ''}
                                    onChange={(e) => {
                                        const next = categories.find((c) => c.id === Number(e.target.value));
                                        setData('parent_id', next?.id ?? null);
                                        setData('category_id', next?.slug === 'drugoe' ? (next.children[0]?.id ?? null) : null);
                                    }}
                                >
                                    <option value="">Выберите категорию</option>
                                    {categories.map((c) => (
                                        <option key={c.id} value={c.id}>
                                            {c.name}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            {parent && isOther && (
                                <div className="field">
                                    <label className="label" htmlFor="w-custom-cat">
                                        Своя категория <span className="req">*</span>
                                    </label>
                                    <input
                                        id="w-custom-cat"
                                        className="input"
                                        maxLength={80}
                                        value={data.attributes.custom_category ?? ''}
                                        onChange={(e) =>
                                            setData('attributes', { ...data.attributes, custom_category: e.target.value })
                                        }
                                        placeholder="Например: крепёж и метизы"
                                    />
                                    <p className="hint">
                                        Готовой рубрики нет — назовите категорию своими словами. Она будет видна
                                        на карточке объявления.
                                    </p>
                                </div>
                            )}

                            {parent && !isOther && (
                                <div className="field">
                                    <label className="label" htmlFor="w-sub">
                                        Подкатегория <span className="req">*</span>
                                    </label>
                                    <select
                                        id="w-sub"
                                        className="select"
                                        value={data.category_id ?? ''}
                                        onChange={(e) => setData('category_id', e.target.value ? Number(e.target.value) : null)}
                                    >
                                        <option value="">Выберите подкатегорию</option>
                                        {parent.children.map((c) => (
                                            <option key={c.id} value={c.id}>
                                                {c.name}
                                            </option>
                                        ))}
                                    </select>
                                    {errors.category_id && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.category_id}</p>}
                                </div>
                            )}

                            <div className="field">
                                <label className="label" htmlFor="w-title">
                                    Заголовок <span className="req">*</span>
                                </label>
                                <input
                                    id="w-title"
                                    className="input"
                                    maxLength={90}
                                    value={data.title}
                                    onChange={(e) => setData('title', e.target.value)}
                                    placeholder="Цемент М400 навалом и в мешках 50 кг, отгрузка с завода"
                                />
                                <p className="hint">
                                    {data.title.length} / 90 символов
                                    {titleLeft < 15 && ` · осталось ${titleLeft}`}. Укажите товар, марку и способ
                                    отгрузки — так находят чаще.
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
                                        Поля категории «{child.name}» — подставляются автоматически
                                    </p>
                                    <div className="grid grid-2 grid-tight" style={{ gap: 12 }}>
                                        {child.fields.map((f) => (
                                            <div key={f.key} className="field" style={{ margin: 0 }}>
                                                <label className="label" htmlFor={`w-${f.key}`}>
                                                    {f.label}
                                                </label>
                                                {f.type === 'select' ? (
                                                    <select
                                                        id={`w-${f.key}`}
                                                        className="select"
                                                        value={data.attributes[f.key] ?? ''}
                                                        onChange={(e) =>
                                                            setData('attributes', { ...data.attributes, [f.key]: e.target.value })
                                                        }
                                                    >
                                                        <option value="">Не указано</option>
                                                        {f.options.map((o) => (
                                                            <option key={o} value={o}>
                                                                {o}
                                                            </option>
                                                        ))}
                                                    </select>
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
                                    Далее: товар и цена
                                </button>
                            </div>
                        </>
                    )}

                    {step === 2 && (
                        <>
                            <h2 className="t-h3" style={{ marginBottom: 16 }}>
                                Описание и цена
                            </h2>

                            <div className="field">
                                <label className="label" htmlFor="w-desc">
                                    Описание <span className="req">*</span>
                                </label>
                                <textarea
                                    id="w-desc"
                                    className="textarea"
                                    maxLength={5000}
                                    value={data.description}
                                    onChange={(e) => setData('description', e.target.value)}
                                    placeholder="Расскажите об условиях, объёмах, гарантиях качества…"
                                />
                                <p className="hint">
                                    {data.description.length} / 5000{descLeft < 200 && ` · осталось ${descLeft}`}.
                                    Телефоны, почта и ссылки будут автоматически скрыты — контакты передаются только
                                    через площадку.
                                </p>
                                {errors.description && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.description}</p>}
                            </div>

                            <div className="grid grid-2 grid-tight mt-24" style={{ gap: 12 }}>
                                <div className="field" style={{ margin: 0 }}>
                                    <label className="label" htmlFor="w-price">
                                        Цена за единицу
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
                                        Валюта
                                    </label>
                                    <select
                                        id="w-cur"
                                        className="select"
                                        value={data.currency}
                                        onChange={(e) => setData('currency', e.target.value)}
                                    >
                                        <option value="UZS">сум (UZS)</option>
                                        <option value="USD">доллар (USD)</option>
                                    </select>
                                </div>
                            </div>

                            <div className="grid grid-2 grid-tight mt-12" style={{ gap: 12 }}>
                                <div className="field" style={{ margin: 0 }}>
                                    <label className="label" htmlFor="w-unit">
                                        Единица измерения
                                    </label>
                                    <input
                                        id="w-unit"
                                        className="input"
                                        value={data.unit}
                                        onChange={(e) => setData('unit', e.target.value)}
                                        placeholder="т, м³, шт"
                                    />
                                </div>
                                <div className="field" style={{ margin: 0 }}>
                                    <label className="label" htmlFor="w-min">
                                        Минимальная партия
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
                                Цена договорная — не показывать сумму
                            </label>
                            {errors.price && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.price}</p>}

                            <div className="row mt-32" style={{ gap: 10 }}>
                                <button className="btn btn-secondary" onClick={() => go(1)}>
                                    Назад
                                </button>
                                <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => go(3)}>
                                    Далее: условия
                                </button>
                            </div>
                        </>
                    )}

                    {step === 3 && (
                        <>
                            <h2 className="t-h3" style={{ marginBottom: 16 }}>
                                Условия поставки и оплаты
                            </h2>

                            <div className="field">
                                <label className="label" htmlFor="w-delivery">
                                    Условия поставки
                                </label>
                                <textarea
                                    id="w-delivery"
                                    className="textarea"
                                    style={{ minHeight: 90 }}
                                    value={data.delivery_terms}
                                    onChange={(e) => setData('delivery_terms', e.target.value)}
                                    placeholder="Самовывоз со склада, доставка по Ташкентской области, отгрузка в течение 2 дней"
                                />
                            </div>

                            <div className="field">
                                <label className="label" htmlFor="w-payment">
                                    Условия оплаты
                                </label>
                                <textarea
                                    id="w-payment"
                                    className="textarea"
                                    style={{ minHeight: 90 }}
                                    value={data.payment_terms}
                                    onChange={(e) => setData('payment_terms', e.target.value)}
                                    placeholder="Предоплата 50 %, остаток по факту отгрузки. Работаем с НДС"
                                />
                            </div>

                            <div className="row mt-32" style={{ gap: 10 }}>
                                <button className="btn btn-secondary" onClick={() => go(2)}>
                                    Назад
                                </button>
                                <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => go(4)}>
                                    Далее: фото
                                </button>
                            </div>
                        </>
                    )}

                    {step === 4 && (
                        <>
                            <h2 className="t-h3" style={{ marginBottom: 16 }}>
                                Фото и документы
                            </h2>

                            <PhotoUploader listingId={listing.id} photos={listing.images} />

                            {problems.length > 0 ? (
                                <div className="alert alert-danger mt-24">
                                    <TriangleAlert aria-hidden className="size-5" />
                                    <div>
                                        <b>Объявление не отправлено на проверку</b>
                                        <ul className="stack-8 mt-8">
                                            {problems.map((p) => (
                                                <li key={p.field}>
                                                    {p.message}{' '}
                                                    <button
                                                        type="button"
                                                        className="link"
                                                        onClick={() => go(p.step)}
                                                    >
                                                        Шаг {p.step}: {STEPS[p.step - 1]}
                                                    </button>
                                                </li>
                                            ))}
                                        </ul>
                                        <p className="t-sm mt-8">
                                            Введённое сохранено в черновике — исправьте и нажмите «Опубликовать» ещё раз.
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <div className="alert alert-info mt-24">
                                    <Check aria-hidden className="size-5" />
                                    <div>
                                        После публикации объявление уходит на модерацию — обычно до 2 часов в рабочее
                                        время.
                                    </div>
                                </div>
                            )}

                            <div className="row mt-32" style={{ gap: 10 }}>
                                <button className="btn btn-secondary" onClick={() => go(3)}>
                                    Назад
                                </button>
                                <button className="btn btn-primary" style={{ flex: 1 }} disabled={processing} onClick={publish}>
                                    {processing ? 'Отправляем…' : 'Опубликовать'}
                                </button>
                            </div>
                        </>
                    )}
                </div>

                <aside className="stack-16">
                    <div className="card">
                        <h3 className="t-h4" style={{ marginBottom: 12 }}>
                            Как получить больше откликов
                        </h3>
                        <ul className="stack-12 t-sm">
                            {TIPS.map((tip) => (
                                <li key={tip} className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                                    <Check aria-hidden className="size-4 shrink-0" style={{ color: 'var(--success)', marginTop: 4 }} />
                                    {tip}
                                </li>
                            ))}
                        </ul>
                    </div>

                    <div className="card" style={{ background: 'var(--primary-50)', borderColor: 'var(--primary-100)' }}>
                        <p className="t-sm">
                            <b>Осталось слотов:</b>{' '}
                            {slots.total === null ? 'без ограничений' : `${slots.total - slots.used} из ${slots.total}`}
                        </p>
                        <p className="t-sm muted mt-8">Черновики слот не занимают — только опубликованные объявления.</p>
                    </div>

                    <button
                        className="btn btn-ghost btn-block"
                        onClick={() =>
                            confirm({
                                title: 'Удалить черновик?',
                                description: 'Введённый текст и загруженные фотографии будут потеряны безвозвратно.',
                                confirmLabel: 'Удалить черновик',
                                danger: true,
                                onConfirm: () => router.delete(`/cabinet/listings/${listing.id}`),
                            })
                        }
                    >
                        Удалить черновик
                    </button>
                </aside>
            </div>
        </CabinetLayout>
    );
}
