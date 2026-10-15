import { useForm, usePage } from '@inertiajs/react';
import { Check, Loader2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { IlmoraLayout } from '@/components/ilmora/IlmoraLayout';
import { Link } from '@/components/ui/Link';
import { t } from '@/lib/i18n';
import { localize } from '@/lib/locale';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';
import { formatPhone, phoneDigits, validateIlmora, type IlmoraForm } from './rules';

/**
 * Регистрация в ILMORA через Savdex (python/savdex/ilmora/views.py).
 * Телефон, ФИО, физлицо или юрлицо с ПИНФЛ или ИНН и две галочки оферты.
 * Ошибки показываются сразу, но решает сервер. После отправки —
 * «Заявка принята» и кнопка в ILMORA; аккаунт Savdex не заводится.
 */
export default function IlmoraRegister({
    done = false,
    ilmoraUrl,
    phonePrefix = '+998',
}: {
    done?: boolean;
    ilmoraUrl: string;
    phonePrefix?: string;
}) {
    return (
        <IlmoraLayout title={t('ilmora.title')}>
            <div className="ilmora-card">
                {done ? (
                    <Done url={ilmoraUrl} />
                ) : (
                    <RegisterForm phonePrefix={phonePrefix} />
                )}
            </div>

            <Link href={routes.register} className="ilmora-back">
                ← {t('ilmora.back')}
            </Link>
        </IlmoraLayout>
    );
}

function Done({ url }: { url: string }) {
    return (
        <div className="ilmora-done">
            <span className="ilmora-done__icon" aria-hidden>
                <Check className="size-8" strokeWidth={2.2} />
            </span>
            <h1 className="ilmora-title">{t('ilmora.done_title')}</h1>
            <p className="ilmora-sub">{t('ilmora.done_text')}</p>
            <a href={url} className="ilmora-button" rel="noopener">
                {t('ilmora.done_button')}
            </a>
        </div>
    );
}

type Field = keyof IlmoraForm;

function RegisterForm({ phonePrefix }: { phonePrefix: string }) {
    const { flash } = usePage<SharedProps>().props;
    const { data, setData, post, processing, errors, setError, clearErrors, transform } = useForm<IlmoraForm>({
        phone: '',
        full_name: '',
        person_type: '',
        pinfl: '',
        tin: '',
        offer_read: false,
        offer_sign: false,
    });
    // Поля, которые человек уже покинул: ошибка под ними — сразу, не дожидаясь отправки
    const [touched, setTouched] = useState<Partial<Record<Field, boolean>>>({});
    const [submitted, setSubmitted] = useState(false);

    const client = validateIlmora(data);
    const shown = (field: Field): string | undefined =>
        (errors as Partial<Record<Field, string>>)[field] ??
        (submitted || touched[field] ? client[field] : undefined);

    function change<K extends Field>(field: K, value: IlmoraForm[K]) {
        setData((was) => ({ ...was, [field]: value }));
        clearErrors(field);
    }

    const leave = (field: Field) => () => setTouched((was) => ({ ...was, [field]: true }));

    // На сервер — только номер выбранного вида лица
    transform((form) => ({
        ...form,
        pinfl: form.person_type === 'individual' ? form.pinfl : '',
        tin: form.person_type === 'legal' ? form.tin : '',
    }));

    function submit(e: FormEvent) {
        e.preventDefault();
        setSubmitted(true);

        const found = validateIlmora(data);

        if (Object.keys(found).length > 0) {
            setError(found as Record<Field, string>);
            document.querySelector<HTMLElement>(`[data-field="${Object.keys(found)[0]}"]`)?.focus();

            return;
        }

        post(routes.ilmoraRegister);
    }

    const [before, after] = t('ilmora.offer_read').split(':offer');

    return (
        <>
            <h1 className="ilmora-title">{t('ilmora.heading')}</h1>
            <p className="ilmora-sub">{t('ilmora.subheading')}</p>

            {flash?.error && (
                <p className="ilmora-alert" role="alert">
                    {flash.error}
                </p>
            )}

            <form onSubmit={submit} className="ilmora-form" noValidate>
                <div className="ilmora-field">
                    <label className="ilmora-label" htmlFor="ilmora-phone">
                        {t('ilmora.phone')}
                    </label>
                    <div className="ilmora-phone" data-invalid={Boolean(shown('phone'))}>
                        {/* Префикс — не часть поля: стереть его нельзя */}
                        <span className="ilmora-phone__prefix" aria-hidden>
                            {phonePrefix}
                        </span>
                        <input
                            id="ilmora-phone"
                            data-field="phone"
                            className="ilmora-input"
                            type="tel"
                            inputMode="numeric"
                            autoComplete="tel-national"
                            placeholder="99 222 33 44"
                            aria-label={`${t('ilmora.phone')} ${phonePrefix}`}
                            aria-invalid={Boolean(shown('phone'))}
                            aria-describedby="ilmora-phone-note"
                            value={formatPhone(data.phone)}
                            onChange={(e) => change('phone', phoneDigits(e.target.value))}
                            onBlur={leave('phone')}
                        />
                    </div>
                    <Note id="ilmora-phone-note" error={shown('phone')} hint={t('ilmora.phone_hint')} />
                </div>

                <div className="ilmora-field">
                    <label className="ilmora-label" htmlFor="ilmora-name">
                        {t('ilmora.full_name')}
                    </label>
                    <input
                        id="ilmora-name"
                        data-field="full_name"
                        className="ilmora-input"
                        type="text"
                        autoComplete="name"
                        maxLength={200}
                        placeholder={t('ilmora.full_name_placeholder')}
                        aria-invalid={Boolean(shown('full_name'))}
                        aria-describedby="ilmora-name-note"
                        value={data.full_name}
                        onChange={(e) => change('full_name', e.target.value)}
                        onBlur={leave('full_name')}
                    />
                    <Note id="ilmora-name-note" error={shown('full_name')} hint={t('ilmora.full_name_hint')} />
                </div>

                <fieldset className="ilmora-field">
                    <legend className="ilmora-label mb-1.5">{t('ilmora.person_type')}</legend>
                    <div className="ilmora-switch" data-invalid={Boolean(shown('person_type'))}>
                        {(['individual', 'legal'] as const).map((kind, i) => (
                            <label key={kind}>
                                <input
                                    type="radio"
                                    name="person_type"
                                    value={kind}
                                    data-field={i === 0 ? 'person_type' : undefined}
                                    checked={data.person_type === kind}
                                    onChange={() => change('person_type', kind)}
                                />
                                {t(`ilmora.${kind}`)}
                            </label>
                        ))}
                    </div>
                    <Note id="ilmora-type-note" error={shown('person_type')} />
                </fieldset>

                {data.person_type === 'individual' && (
                    <NumberField
                        field="pinfl"
                        label={t('ilmora.pinfl')}
                        hint={t('ilmora.pinfl_hint')}
                        max={14}
                        value={data.pinfl}
                        error={shown('pinfl')}
                        onChange={(value) => change('pinfl', value)}
                        onBlur={leave('pinfl')}
                    />
                )}

                {data.person_type === 'legal' && (
                    <NumberField
                        field="tin"
                        label={t('ilmora.tin')}
                        hint={t('ilmora.tin_hint')}
                        max={9}
                        value={data.tin}
                        error={shown('tin')}
                        onChange={(value) => change('tin', value)}
                        onBlur={leave('tin')}
                    />
                )}

                <div className="ilmora-field">
                    <label className="ilmora-check">
                        <input
                            type="checkbox"
                            data-field="offer_read"
                            checked={data.offer_read}
                            aria-invalid={Boolean(shown('offer_read'))}
                            aria-describedby="ilmora-read-note"
                            onChange={(e) => change('offer_read', e.target.checked)}
                        />
                        <span>
                            {before}
                            {/* В новой вкладке: заполненная форма не теряется */}
                            <a href={localize(routes.ilmoraOffer)} target="_blank" rel="noopener">
                                {t('ilmora.offer_link')}
                            </a>
                            {after}
                        </span>
                    </label>
                    <Note id="ilmora-read-note" error={shown('offer_read')} />
                </div>

                <div className="ilmora-field">
                    <label className="ilmora-check">
                        <input
                            type="checkbox"
                            data-field="offer_sign"
                            checked={data.offer_sign}
                            aria-invalid={Boolean(shown('offer_sign'))}
                            aria-describedby="ilmora-sign-note"
                            onChange={(e) => change('offer_sign', e.target.checked)}
                        />
                        <span>{t('ilmora.offer_sign')}</span>
                    </label>
                    <Note id="ilmora-sign-note" error={shown('offer_sign')} />
                </div>

                <button type="submit" className="ilmora-button" disabled={processing}>
                    {processing && <Loader2 aria-hidden className="size-4 animate-spin" />}
                    {t('ilmora.submit')}
                </button>
            </form>
        </>
    );
}

function NumberField({
    field,
    label,
    hint,
    max,
    value,
    error,
    onChange,
    onBlur,
}: {
    field: 'pinfl' | 'tin';
    label: string;
    hint: string;
    max: number;
    value: string;
    error?: string;
    onChange: (value: string) => void;
    onBlur: () => void;
}) {
    const id = `ilmora-${field}`;

    return (
        <div className="ilmora-field">
            <label className="ilmora-label" htmlFor={id}>
                {label}
            </label>
            <input
                id={id}
                data-field={field}
                className="ilmora-input"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                // С запасом: лишняя цифра должна быть видна в ошибке («введено 15»)
                maxLength={max + 6}
                aria-invalid={Boolean(error)}
                aria-describedby={`${id}-note`}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                onBlur={onBlur}
            />
            <Note id={`${id}-note`} error={error} hint={hint} />
        </div>
    );
}

/** Под полем: ошибка, а без неё — подсказка */
function Note({ id, error, hint }: { id: string; error?: string; hint?: string }) {
    if (error) {
        return (
            <p id={id} className="ilmora-error" role="alert">
                {error}
            </p>
        );
    }

    return hint ? (
        <p id={id} className="ilmora-hint">
            {hint}
        </p>
    ) : null;
}
