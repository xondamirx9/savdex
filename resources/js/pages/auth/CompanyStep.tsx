import { useForm } from '@inertiajs/react';
import { X } from 'lucide-react';
import type { FormEvent } from 'react';
import { Button, TextInput } from '@/components/ui';
import { CountryField } from '@/components/CountryField';
import { SelectField } from '@/components/SelectField';
import { countryCode, tinInputMode, tinLabel, type CountryOption } from '@/lib/countries';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
import { localize } from '@/lib/locale';
import { cn } from '@/lib/cn';

interface Props {
    countries: CountryOption[];
    cities: { id: number; name: string; country_id: number }[];
    categories: { id: number; slug: string; name: string }[];
    serviceCategories: { id: number; slug: string; name: string }[];
    types: Record<string, string>;
    /** Выбор с первого шага: юрлицо, физлицо или фрилансер. */
    accountType?: 'legal' | 'individual' | 'freelancer';
    /** Имя из регистрации — готовое имя профиля физлица и фрилансера. */
    personName?: string;
    /**
     * Компания заведена при регистрации юрлица: название, ИНН
     * и категории уже есть — шаг спрашивает только недостающее.
     */
    completing?: boolean;
    /** Страна, выбранная при регистрации; нет — человек выбирает сам. */
    countryId?: number | null;
}

/**
 * Роли на площадке. Функция, а не константа модуля: подписи берутся
 * из словаря, а он приходит с сервером после загрузки файла.
 */
const roles = (): [string, string, string][] => [
    ['supplier', t('auth.role_supplier'), t('auth.role_supplier_desc')],
    ['buyer', t('auth.role_buyer'), t('auth.role_buyer_desc')],
    ['both', t('auth.role_both'), t('auth.role_both_desc')],
];

/** Код типа «Услуги» из справочника — он заводится в админке. */
function serviceTypeKey(types: Record<string, string>): string {
    return ['service', 'services', 'uslugi'].find((k) => k in types) ?? '';
}

/**
 * Второй шаг регистрации — данные компании.
 *
 * Шаг пропускаемый: аккаунт уже создан, и терять человека из-за
 * незаполненного ИНН нельзя. Но заполнить его выгодно, и об этом
 * сказано числом, а не уговорами.
 */
export default function CompanyStep({
    countries,
    cities,
    categories,
    serviceCategories,
    types,
    accountType = 'legal',
    personName = '',
    completing = false,
    countryId = null,
}: Props) {
    // Физлицо и фрилансер выступают от своего имени: без названия
    // компании и обязательного типа бизнеса, ИНН или ПИНФЛ — по желанию
    const person = accountType !== 'legal';

    const { data, setData, post, processing, errors } = useForm<{
        name: string;
        type: string;
        country_id: number | null;
        city_id: number | null;
        tin: string;
        primary_role: string;
        categories: number[];
        custom_category: string;
    }>({
        name: person ? personName : '',
        // Фрилансер оказывает услуги — сразу открываем их направления
        type: accountType === 'freelancer' ? serviceTypeKey(types) : person ? '' : 'distributor',
        // Без молчаливого «Узбекистана»: страну выбирает человек (ТЗ-02)
        country_id: countryId,
        city_id: null,
        tin: '',
        primary_role: 'both',
        categories: [],
        custom_category: '',
    });

    /*
     * Тип «Услуги» открывает блок направлений (эйчар, финансы
     * и бухгалтерия…). Код типа приходит из справочника админки,
     * поэтому проверяем известные варианты, а не одно значение.
     */
    const isServiceType = ['service', 'services', 'uslugi'].includes(data.type);

    const allCategories = [...categories, ...serviceCategories];

    const needsCustomText = allCategories.some(
        (c) => (c.slug === 'drugoe' || c.slug === 'uslugi-drugoe') && data.categories.includes(c.id),
    );

    const availableCities = cities.filter((c) => c.country_id === data.country_id);
    // Узбекский ИНН (и ПИНФЛ физлица) — свои подписи; у других стран — свой номер
    const uzOrUnknown = ['uz', null].includes(countryCode(countries, data.country_id));

    function toggleCategory(id: number) {
        setData(
            'categories',
            data.categories.includes(id)
                ? data.categories.filter((c) => c !== id)
                : // Больше пяти категорий — профиль перестаёт что-либо
                  // говорить о компании, поэтому предел жёсткий
                  data.categories.length >= 5
                  ? data.categories
                  : [...data.categories, id],
        );
    }

    function submit(e: FormEvent) {
        e.preventDefault();
        post('/onboarding/company');
    }

    return (
        <AuthLayout
            title={person ? t('auth.person_title') : t('auth.company_title')}
            heading={person ? t('auth.person_title') : t('auth.company_title')}
            subheading={person ? t('auth.person_subheading') : t('auth.company_subheading')}
        >
            <form onSubmit={submit} className="space-y-5" noValidate>
                {/* Страна — первой: от неё зависят город и правила номера (ТЗ-02) */}
                <div className="grid grid-2 grid-tight" style={{ gap: 12 }}>
                    <CountryField
                        id="c-country"
                        countries={countries}
                        value={data.country_id}
                        onChange={(id) => {
                            setData('country_id', id);
                            // Город из другой страны — рассинхрон,
                            // который потом ищут в данных руками
                            setData('city_id', null);
                        }}
                        error={errors.country_id}
                    />

                    <div className="field" style={{ margin: 0 }}>
                        <label className="label" htmlFor="c-city">
                            {t('auth.city_label')} <span className="req">*</span>
                        </label>
                        <SelectField
                            id="c-city"
                            ariaLabel={t('auth.city_label')}
                            value={String(data.city_id ?? '')}
                            onChange={(value) => setData('city_id', value ? Number(value) : null)}
                            placeholder={t('auth.city_choose')}
                            options={availableCities.map((c) => ({ value: String(c.id), label: c.name }))}
                        />
                        {errors.city_id && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.city_id}</p>}
                    </div>
                </div>

                {!completing && (
                    <TextInput
                        label={person ? t('auth.person_name_label') : t('auth.company_name_label')}
                        name="name"
                        required
                        placeholder={
                            accountType === 'freelancer'
                                ? t('auth.freelancer_name_placeholder')
                                : person
                                  ? t('auth.person_name_placeholder')
                                  : t('auth.company_name_placeholder')
                        }
                        value={data.name}
                        onChange={(e) => setData('name', e.target.value)}
                        error={errors.name}
                        autoFocus
                    />
                )}

                <div className="field">
                    <label className="label" htmlFor="c-type">
                        {person ? t('auth.person_type_label') : t('auth.company_type_label')}
                        {!person && <span className="req"> *</span>}
                    </label>
                    <SelectField
                        id="c-type"
                        ariaLabel={person ? t('auth.person_type_label') : t('auth.company_type_label')}
                        value={data.type}
                        onChange={(value) => setData('type', value)}
                        options={[
                            ...(person ? [{ value: '', label: t('auth.person_type_none') }] : []),
                            ...Object.entries(types).map(([key, label]) => ({ value: key, label })),
                        ]}
                    />
                    {errors.type && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.type}</p>}
                </div>

                {isServiceType && serviceCategories.length > 0 && (
                    <div className="field">
                        <span className="label">{t('auth.service_categories_label')}</span>
                        <div className="row wrap" style={{ gap: 6 }}>
                            {serviceCategories.map((c) => (
                                <button
                                    key={c.id}
                                    type="button"
                                    className={cn('chip', data.categories.includes(c.id) && 'chip-active')}
                                    onClick={() => toggleCategory(c.id)}
                                >
                                    {c.name}
                                </button>
                            ))}
                        </div>
                        <p className="hint">{t('auth.service_categories_hint')}</p>
                    </div>
                )}

                {!completing && (
                    <TextInput
                        label={
                            person && uzOrUnknown ? t('auth.person_tin_label') : tinLabel(countryCode(countries, data.country_id))
                        }
                        name="tin"
                        inputMode={tinInputMode(countryCode(countries, data.country_id))}
                        placeholder={
                            !uzOrUnknown ? undefined : person ? t('auth.person_tin_placeholder') : t('auth.tin_placeholder')
                        }
                        value={data.tin}
                        onChange={(e) => setData('tin', e.target.value)}
                        error={errors.tin}
                        hint={person ? t('auth.person_tin_hint') : t('auth.tin_hint')}
                    />
                )}

                <fieldset style={{ border: 'none' }}>
                    <legend className="label" style={{ marginBottom: 8 }}>
                        {t('auth.role_legend')} <span className="req">*</span>
                    </legend>
                    <div className="radio-cards">
                        {roles().map(([value, title, desc]) => (
                            <label key={value} className="radio-card">
                                <input
                                    type="radio"
                                    name="primary_role"
                                    checked={data.primary_role === value}
                                    onChange={() => setData('primary_role', value)}
                                />
                                <div className="radio-card-body">
                                    <div className="radio-card-title">{title}</div>
                                    <div className="radio-card-desc">{desc}</div>
                                </div>
                            </label>
                        ))}
                    </div>
                </fieldset>

                {!completing && (
                    <div className="field">
                        <label className="label" htmlFor="c-cats">
                            {t('auth.categories_label')}
                        </label>
                        <SelectField
                            id="c-cats"
                            ariaLabel={t('auth.categories_add')}
                            value=""
                            onChange={(value) => value && toggleCategory(Number(value))}
                            placeholder={t('auth.categories_add')}
                            options={categories
                                .filter((c) => !data.categories.includes(c.id))
                                .map((c) => ({ value: String(c.id), label: c.name }))}
                        />

                        {data.categories.some((id) => categories.some((c) => c.id === id)) && (
                            <div className="row wrap mt-8" style={{ gap: 6 }}>
                                {data.categories
                                    .filter((id) => categories.some((c) => c.id === id))
                                    .map((id) => {
                                    const category = allCategories.find((c) => c.id === id);
                                    return (
                                        <button
                                            key={id}
                                            type="button"
                                            className="chip chip-active"
                                            onClick={() => toggleCategory(id)}
                                        >
                                            {category?.name}
                                            <X aria-hidden className="size-3.5" />
                                        </button>
                                    );
                                })}
                            </div>
                        )}

                        {/* «Другое» выбрано — компания называет направление сама.
                            Текст виден на визитке рядом с типом компании */}
                        {needsCustomText && (
                            <div className="mt-8">
                                <input
                                    className="input"
                                    maxLength={80}
                                    value={data.custom_category}
                                    onChange={(e) => setData('custom_category', e.target.value)}
                                    placeholder={t('auth.custom_category_placeholder')}
                                    aria-label={t('auth.custom_category_aria')}
                                />
                                {errors.custom_category && (
                                    <p className="hint" style={{ color: 'var(--danger)' }}>{errors.custom_category}</p>
                                )}
                            </div>
                        )}

                        <p className={cn('hint', data.categories.length >= 5 && 'text-warning')}>
                            {data.categories.length >= 5
                                ? t('auth.categories_limit')
                                : t('auth.categories_hint')}
                        </p>
                        {errors.categories && (
                            <p className="hint" style={{ color: 'var(--danger)' }}>{errors.categories}</p>
                        )}
                    </div>
                )}

                <Button type="submit" size="lg" block loading={processing}>
                    {t('auth.continue')}
                </Button>
            </form>

            {/* Пропуск обязателен: аккаунт уже создан, и упереться
                в форму на этом шаге — потерять человека совсем */}
            <form method="post" action={localize('/onboarding/skip')} className="mt-8">
                <button
                    type="button"
                    className="btn btn-ghost btn-block btn-sm"
                    onClick={() => post('/onboarding/skip')}
                >
                    {t('auth.fill_later')}
                </button>
            </form>
        </AuthLayout>
    );
}
