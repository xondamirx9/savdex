import { useForm } from '@inertiajs/react';
import { MailCheck, X } from 'lucide-react';
import { RegisterSteps } from '@/components/auth/RegisterSteps';
import { Link } from '@/components/ui/Link';
import { useMemo, type FormEvent } from 'react';
import { Button, PasswordInput, TextInput } from '@/components/ui';
import { CountryField } from '@/components/CountryField';
import { SelectField } from '@/components/SelectField';
import { countryCode, tinInputMode, tinLabel, type CountryOption } from '@/lib/countries';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
import { localize } from '@/lib/locale';
import { routes } from '@/routes';
import { cn } from '@/lib/cn';

/** Длина пароля — как у сервера (Password::defaults в AppServiceProvider). */
const PASSWORD_MIN = 8;
const PASSWORD_MAX = 20;

/**
 * Оценка надёжности пароля 0–4.
 * Правила совпадают с серверными (RegisterRequest): от 8 до 20 символов,
 * буквы и цифры. Клиент только подсказывает заранее — решение всё равно
 * принимает сервер, иначе проверку обойдут отключением JavaScript.
 */
function scorePassword(v: string): number {
    let s = 0;
    if (v.length >= PASSWORD_MIN) s++;
    if (v.length >= 12) s++;
    if (/[a-zа-я]/.test(v) && /[A-ZА-Я]/.test(v)) s++;
    if (/\d/.test(v)) s++;
    if (/[^\w\s]/.test(v)) s++;
    if (/^(123|qwe|password|пароль|admin)/i.test(v)) s = Math.min(s, 1);
    return Math.min(s, 4);
}

/**
 * Кто регистрируется. Функция, а не константа модуля: подписи берутся
 * из словаря, а он приходит с сервером после загрузки файла.
 */
const accountTypes = (): [string, string, string][] => [
    ['legal', t('auth.account_legal'), t('auth.account_legal_desc')],
    ['individual', t('auth.account_individual'), t('auth.account_individual_desc')],
    ['freelancer', t('auth.account_freelancer'), t('auth.account_freelancer_desc')],
];

interface Props {
    /** Почта, подтверждённая кодом на втором шаге. */
    email?: string;
    /** Разделы каталога — «Категория» юрлица. */
    categories?: { id: number; name: string }[];
    /** Направления «Доп. услуг» — «Категория» фрилансера. */
    serviceSections?: { code: string; label: string }[];
    /** Страна юрлица — от неё зависит, как проверяется номер компании. */
    countries?: CountryOption[];
}

/** Больше пяти категорий — профиль перестаёт что-либо говорить о компании. */
const MAX_CATEGORIES = 5;

const BARS = ['bg-danger', 'bg-danger', 'bg-warning', 'bg-success', 'bg-success'];
const TEXTS = ['text-danger', 'text-danger', 'text-warning', 'text-success', 'text-success'];

export default function Register({ email = '', categories = [], serviceSections = [], countries = [] }: Props) {
    const { data, setData, post, processing, errors, clearErrors } = useForm({
        // Юрлицо: страна, компания и её категории
        country_id: null as number | null,
        company_name: '',
        tin: '',
        categories: [] as number[],
        // Физлицо и фрилансер: ПИНФЛ; фрилансер — ещё направление услуг
        pinfl: '',
        service_section: '',
        name: '',
        phone: '',
        password: '',
        password_confirmation: '',
        terms: false as boolean,
        // Юрлицо — по умолчанию: площадка B2B, и большинство
        // регистрируются от компании
        account_type: 'legal',
    });

    /**
     * Гасит ошибку поля, как только человек начал его править.
     * Красная подпись, висящая под полем, которое уже исправлено, читается
     * как «всё ещё неверно» и заставляет искать несуществующую проблему.
     */
    function update<K extends keyof typeof data>(key: K, value: (typeof data)[K]) {
        setData((d) => ({ ...d, [key]: value }));

        if (key === 'password' || key === 'password_confirmation') {
            // Несовпадение — ошибка пары, а не одного поля
            clearErrors('password', 'password_confirmation');
        } else if (errors[key as keyof typeof errors]) {
            clearErrors(key as keyof typeof errors);
        }
    }

    const legal = data.account_type === 'legal';
    const code = countryCode(countries, data.country_id);
    const uzOrUnknown = code === null || code === 'uz';
    const phoneCode = countries.find((c) => c.id === data.country_id)?.phone_code ?? null;
    const freelancer = data.account_type === 'freelancer';

    function toggleCategory(id: number) {
        const next = data.categories.includes(id)
            ? data.categories.filter((c) => c !== id)
            : data.categories.length >= MAX_CATEGORIES
              ? data.categories
              : [...data.categories, id];
        update('categories', next);
    }

    const strength = useMemo(() => {
        if (!data.password) return null;
        const score = scorePassword(data.password);
        // Только то, без чего сервер пароль не примет. Спецсимвол сюда
        // не входит: он повышает оценку, но не обязателен, и «добавьте
        // спецсимвол» читалось как требование, а про букву молчало
        const missing: string[] = [];
        if (data.password.length < PASSWORD_MIN) {
            missing.push(t('auth.missing_length', { count: PASSWORD_MIN - data.password.length }));
        }
        if (!/\p{L}/u.test(data.password)) missing.push(t('auth.missing_letter'));
        if (!/\p{N}/u.test(data.password)) missing.push(t('auth.missing_digit'));
        return { score, missing };
    }, [data.password]);

    const tooLong = data.password.length > PASSWORD_MAX;

    function submit(e: FormEvent) {
        e.preventDefault();

        // Без согласия с офертой кнопка неактивна; проверка здесь — на случай
        // отправки формы клавишей Enter из поля
        if (!data.terms) return;

        post(routes.register, {
            // Пароль стирается, только если отклонён он сам. Раньше оба поля
            // очищались после любой ошибки — опечатка в телефоне стоила
            // повторного набора двух паролей по десять знаков
            onError: (errs) => {
                if (errs.password || errs.password_confirmation) {
                    setData((d) => ({ ...d, password: '', password_confirmation: '' }));
                }
            },
        });
    }

    return (
        <AuthLayout
            wide
            title={t('auth.register_title')}
            heading={t('auth.register_heading')}
            subheading={t('auth.register_subheading')}
        >
            <RegisterSteps current={3} />

            {/* Почта уже подтверждена кодом — здесь её только показываем */}
            <div className="bg-primary-50 rounded-card mb-5 flex items-center gap-3 p-3.5 text-sm">
                <MailCheck aria-hidden className="text-primary-700 size-5 shrink-0" />
                <span className="min-w-0">
                    {t('auth.reg_email_verified')}: <b className="break-all">{email}</b>
                </span>
            </div>
            {/* Адрес успели занять между шагами — ошибка почты без поля */}
            {(errors as Record<string, string | undefined>).email && (
                <p className="text-danger -mt-3 mb-5 text-[13px]" role="alert">
                    {(errors as Record<string, string | undefined>).email}
                </p>
            )}

            <form onSubmit={submit} className="space-y-5" noValidate>
                {/* Кто вы: от выбора зависит второй шаг — профиль компании
                    или профиль человека без названия и типа бизнеса */}
                <fieldset style={{ border: 'none' }}>
                    <legend className="label" style={{ marginBottom: 8 }}>
                        {t('auth.account_type_legend')} <span className="req">*</span>
                    </legend>
                    <div className="radio-cards radio-cards--row">
                        {accountTypes().map(([value, title, desc]) => (
                            <label key={value} className="radio-card">
                                <input
                                    type="radio"
                                    name="account_type"
                                    checked={data.account_type === value}
                                    onChange={() => {
                                        update('account_type', value);
                                        // Ошибки полей другого типа к новой форме не относятся
                                        clearErrors();
                                    }}
                                />
                                <div className="radio-card-body">
                                    <div className="radio-card-title">{title}</div>
                                    <div className="radio-card-desc">{desc}</div>
                                </div>
                            </label>
                        ))}
                    </div>
                    {errors.account_type && (
                        <p className="text-danger mt-1.5 text-[13px]">{errors.account_type}</p>
                    )}
                </fieldset>

                {/* Порядок полей — свой у каждого типа: юрлицо начинает
                    с компании, физлицо и фрилансер — с себя */}
                {/* Страна — у всех: по ней проверяется номер (у иностранного
                    фрилансера нет узбекского ПИНФЛ) */}
                <CountryField
                    id="r-country"
                    countries={countries}
                    value={data.country_id}
                    onChange={(id) => {
                        update('country_id', id);
                        // Код страны — сразу в телефон: без него короткие иностранные
                        // номера не набирают 9 цифр и не проходят проверку
                        const dial = countries.find((c) => c.id === id)?.phone_code;
                        const typed = data.phone.trim();
                        const onlyCode = typed === '' || countries.some((c) => c.phone_code && typed === c.phone_code);
                        if (dial && onlyCode) update('phone', `${dial} `);
                    }}
                    error={errors.country_id}
                    hint={t('auth.country_first_hint')}
                />

                {legal && (
                    <>
                        <TextInput
                            label={t('auth.company_name_label')}
                            name="company_name"
                            autoComplete="organization"
                            required
                            placeholder={t('auth.company_name_placeholder')}
                            value={data.company_name}
                            onChange={(e) => update('company_name', e.target.value)}
                            error={errors.company_name}
                            autoFocus
                        />

                        <TextInput
                            label={tinLabel(code)}
                            name="tin"
                            inputMode={tinInputMode(code)}
                            placeholder={
                                code === 'uz' ? t('auth.tin_placeholder') : undefined
                            }
                            value={data.tin}
                            onChange={(e) => update('tin', e.target.value)}
                            error={errors.tin}
                            hint={t('auth.tin_hint')}
                        />
                    </>
                )}

                <TextInput
                    label={t('auth.full_name_label')}
                    name="name"
                    autoComplete="name"
                    required
                    placeholder={t('auth.full_name_placeholder')}
                    value={data.name}
                    onChange={(e) => update('name', e.target.value)}
                    error={errors.name}
                    autoFocus={!legal}
                />

                {!legal && (
                    /* ПИНФЛ — только в Узбекистане; у других стран — свой номер, по желанию */
                    <TextInput
                        label={uzOrUnknown ? t('auth.pinfl_label') : tinLabel(code)}
                        name="pinfl"
                        inputMode={uzOrUnknown ? 'numeric' : tinInputMode(code)}
                        maxLength={20}
                        required={freelancer && uzOrUnknown}
                        placeholder={uzOrUnknown ? t('auth.pinfl_placeholder') : undefined}
                        value={data.pinfl}
                        onChange={(e) => update('pinfl', e.target.value)}
                        error={errors.pinfl}
                        hint={
                            freelancer && uzOrUnknown ? t('auth.pinfl_hint_required') : t('auth.pinfl_hint_optional')
                        }
                    />
                )}

                <TextInput
                    label={t('auth.phone_label')}
                    type="tel"
                    name="phone"
                    autoComplete="tel"
                    required
                    placeholder={
                        phoneCode && phoneCode !== '+998' ? `${phoneCode} …` : t('auth.phone_placeholder')
                    }
                    value={data.phone}
                    onChange={(e) => update('phone', e.target.value)}
                    error={errors.phone}
                    hint={t('auth.phone_hint')}
                />

{legal && (
                    <div className="field">
                        <label className="label" htmlFor="r-cats">
                            {t('auth.reg_categories_label')} <span className="req">*</span>
                        </label>
                        <SelectField
                            id="r-cats"
                            ariaLabel={t('auth.reg_categories_label')}
                            value=""
                            onChange={(value) => value && toggleCategory(Number(value))}
                            placeholder={t('auth.categories_add')}
                            options={categories
                                .filter((c) => !data.categories.includes(c.id))
                                .map((c) => ({ value: String(c.id), label: c.name }))}
                        />
                        {data.categories.length > 0 && (
                            <div className="row wrap mt-8" style={{ gap: 6 }}>
                                {data.categories.map((id) => (
                                    <button
                                        key={id}
                                        type="button"
                                        className="chip chip-active"
                                        onClick={() => toggleCategory(id)}
                                    >
                                        {categories.find((c) => c.id === id)?.name}
                                        <X aria-hidden className="size-3.5" />
                                    </button>
                                ))}
                            </div>
                        )}
                        <p className={cn('hint', data.categories.length >= MAX_CATEGORIES && 'text-warning')}>
                            {data.categories.length >= MAX_CATEGORIES
                                ? t('auth.categories_limit')
                                : t('auth.reg_categories_hint')}
                        </p>
                        {(errors.categories || errors['categories.0' as keyof typeof errors]) && (
                            <p className="hint" style={{ color: 'var(--danger)' }}>
                                {errors.categories ?? errors['categories.0' as keyof typeof errors]}
                            </p>
                        )}
                    </div>
                )}

                {freelancer && (
                    <div className="field">
                        <label className="label" htmlFor="r-section">
                            {t('auth.service_section_label')} <span className="req">*</span>
                        </label>
                        <SelectField
                            id="r-section"
                            ariaLabel={t('auth.service_section_label')}
                            value={data.service_section}
                            onChange={(value) => update('service_section', value)}
                            placeholder={t('auth.service_section_placeholder')}
                            options={serviceSections.map((s) => ({ value: s.code, label: s.label }))}
                        />
                        <p className="hint">{t('auth.service_section_hint')}</p>
                        {errors.service_section && (
                            <p className="hint" style={{ color: 'var(--danger)' }}>{errors.service_section}</p>
                        )}
                    </div>
                )}

                <div>
                    <PasswordInput
                        label={t('auth.password_label')}
                        name="password"
                        autoComplete="new-password"
                        required
                        placeholder={t('auth.password_placeholder')}
                        value={data.password}
                        onChange={(e) => update('password', e.target.value)}
                        error={errors.password}
                        hint={!data.password ? t('auth.password_rules') : undefined}
                    />
                    {/* Больше 20 символов — предупреждение сразу, а не после
                        отправки: вводить дальше можно, но сервер такой пароль
                        не примет */}
                    {tooLong && !errors.password && (
                        <p className="text-danger mt-1.5 text-[13px]" role="alert">
                            {t('auth.password_too_long', { count: data.password.length })}
                        </p>
                    )}
                    {strength && !tooLong && !errors.password && (
                        <div className="mt-2">
                            <div className="bg-canvas h-[5px] overflow-hidden rounded-full">
                                <div
                                    className={cn('h-full rounded-full transition-all', BARS[strength.score])}
                                    style={{ width: `${((strength.score + 1) / 5) * 100}%` }}
                                />
                            </div>
                            <p className="text-muted mt-1.5 text-[13px]">
                                {t('auth.strength_label')}{' '}
                                <b className={TEXTS[strength.score]}>{t(`auth.strength_${strength.score}`)}</b>
                                {strength.missing.length > 0 &&
                                    ` · ${t('auth.strength_add', { list: strength.missing.join(', ') })}`}
                            </p>
                        </div>
                    )}
                </div>

                <PasswordInput
                    label={t('auth.password_confirm_label')}
                    name="password_confirmation"
                    autoComplete="new-password"
                    required
                    value={data.password_confirmation}
                    onChange={(e) => update('password_confirmation', e.target.value)}
                    error={errors.password_confirmation}
                />

                <div>
                    <label
                        className={cn(
                            'flex cursor-pointer items-start gap-2.5 text-sm',
                            errors.terms && 'text-danger',
                        )}
                    >
                        <input
                            type="checkbox"
                            checked={data.terms}
                            onChange={(e) => update('terms', e.target.checked)}
                            aria-invalid={errors.terms ? true : undefined}
                            className={cn(
                                'accent-primary-700 mt-0.5 size-[18px] shrink-0 cursor-pointer',
                                errors.terms && 'outline-danger rounded-xs outline-2 outline-offset-2',
                            )}
                        />
                        {/* Порядок слов зависит от языка (в узбекском и турецком
                            глагол стоит в конце), поэтому фраза собирается из
                            префикса, двух ссылок, союза и суффикса */}
                        <span>
                            {t('auth.terms_prefix')} <a href={localize(routes.terms)} className="text-primary-700 hover:underline">{t('auth.terms_offer')}</a>{' '}
                            {t('auth.terms_and')}{' '}
                            <a href={localize(routes.privacy)} className="text-primary-700 hover:underline">
                                {t('auth.terms_privacy')}
                            </a>
                            {t('auth.terms_suffix')}
                        </span>
                    </label>
                    {errors.terms && <p className="text-danger mt-1.5 text-[13px]">{errors.terms}</p>}
                </div>

                {/* Пока оферта не принята, кнопка серая и не нажимается,
                    а рядом сказано, что нужно сделать */}
                <div>
                    <Button
                        type="submit"
                        size="lg"
                        block
                        loading={processing}
                        disabled={!data.terms}
                        aria-describedby={!data.terms ? 'terms-required' : undefined}
                        className={!data.terms ? 'register-submit-locked' : undefined}
                    >
                        {t('auth.continue')}
                    </Button>
                    {!data.terms && (
                        <p id="terms-required" className="text-muted mt-2 text-center text-[13px]">
                            {t('auth.terms_required')}
                        </p>
                    )}
                </div>
            </form>

            <p className="text-muted mt-6 text-center text-sm">
                {t('auth.have_account')}{' '}
                <Link href={routes.login} className="text-primary-700 hover:underline">
                    {t('auth.login_link')}
                </Link>
            </p>
        </AuthLayout>
    );
}
