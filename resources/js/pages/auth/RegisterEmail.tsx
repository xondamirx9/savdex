import { useForm } from '@inertiajs/react';
import { Mail, Smartphone } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { RegisterSteps } from '@/components/auth/RegisterSteps';
import { CountryField } from '@/components/CountryField';
import { Button, TextInput } from '@/components/ui';
import { Link } from '@/components/ui/Link';
import { AuthLayout } from '@/layouts/AuthLayout';
import { cn } from '@/lib/cn';
import type { CountryOption } from '@/lib/countries';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Регистрация, шаг 1 из 3: способ — почта или телефон, затем страна и адрес.
 * Пришедший впервые видит только две кнопки «Почта» и «Телефон»; выбрал —
 * на том же шаге появляются поля «Страна» и «Электронная почта» или
 * «Страна» и «Телефон». Вернулся со второго шага — поля сразу открыты.
 * Почта: на адрес уходит код, на втором шаге его вводят (для стран
 * с галочкой «Регистрация без кода» можно продолжить без кода).
 * Телефон: код приходит в SMS, почту человек укажет в анкете и
 * подтвердит потом в профиле.
 */
export default function RegisterEmail({
    email,
    countryId = null,
    countries = [],
    phoneAvailable = false,
    method: initialMethod = null,
    phone = null,
}: {
    email?: string | null;
    countryId?: number | null;
    countries?: CountryOption[];
    /** Код по SMS настроен (Telnyx) — есть вкладка «Телефон» */
    phoneAvailable?: boolean;
    /** Уже выбранный способ; null — ещё не выбран (только пришёл) */
    method?: 'email' | 'phone' | null;
    /** Номер, на который код уже уходил («Изменить номер» со второго шага) */
    phone?: string | null;
}) {
    const [method, setMethod] = useState<'email' | 'phone' | null>(phoneAvailable ? initialMethod : 'email');
    const dialOf = (id: number | null) => countries.find((c) => c.id === id)?.phone_code ?? null;
    const { data, setData, post, processing, errors, clearErrors } = useForm<{
        email: string;
        phone: string;
        country_id: number | null;
    }>({
        email: email ?? '',
        phone: phone ?? (dialOf(countryId) ? `${dialOf(countryId)} ` : ''),
        country_id: countryId,
    });
    const byPhone = method === 'phone';

    function submit(e: FormEvent) {
        e.preventDefault();
        post(byPhone ? routes.registerPhone : routes.registerEmail);
    }

    return (
        <AuthLayout
            title={t('auth.register_title')}
            heading={t(
                method === null
                    ? 'auth.reg_choose_heading'
                    : byPhone
                      ? 'auth.reg_phone_heading'
                      : 'auth.reg_email_heading',
            )}
            subheading={t(
                method === null
                    ? 'auth.reg_choose_subheading'
                    : byPhone
                      ? 'auth.reg_phone_subheading'
                      : 'auth.reg_email_subheading',
            )}
        >
            <RegisterSteps current={1} method={method} />

            {phoneAvailable && (
                <div
                    role="radiogroup"
                    aria-label={t('auth.reg_method_label')}
                    className={cn('grid grid-cols-2 gap-3', method !== null && 'mb-6')}
                >
                    {(
                        [
                            ['email', Mail, 'auth.reg_method_email', 'auth.reg_method_email_hint'],
                            ['phone', Smartphone, 'auth.reg_method_phone', 'auth.reg_method_phone_hint'],
                        ] as const
                    ).map(([key, Icon, label, hint]) => {
                        const selected = method === key;

                        return (
                            <button
                                key={key}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                onClick={() => {
                                    setMethod(key);
                                    clearErrors();
                                }}
                                className={cn(
                                    'rounded-card flex flex-col items-center gap-2 border px-3 text-center transition',
                                    'focus-visible:ring-primary-500 focus-visible:ring-2 focus-visible:outline-none',
                                    // Пока не выбрано — крупные карточки; выбрано — компактный переключатель
                                    method === null ? 'py-6' : 'py-3.5',
                                    selected
                                        ? 'border-primary-700 bg-primary-50 text-primary-900'
                                        : 'bg-surface border-line hover:border-line-strong',
                                )}
                            >
                                <span
                                    className={cn(
                                        'flex items-center justify-center rounded-full',
                                        method === null ? 'size-12' : 'size-9',
                                        selected ? 'bg-primary-700 text-white' : 'bg-primary-50 text-primary-700',
                                    )}
                                >
                                    <Icon aria-hidden className={method === null ? 'size-6' : 'size-5'} />
                                </span>
                                <span className="text-[15px] font-semibold">{t(label)}</span>
                                {method === null && <span className="text-muted text-xs">{t(hint)}</span>}
                            </button>
                        );
                    })}
                </div>
            )}

            {method !== null && (
                <form onSubmit={submit} className="space-y-5" noValidate>
                    <CountryField
                        id="register-country"
                        countries={countries}
                        value={data.country_id}
                        onChange={(id) => {
                            setData((prev) => {
                                // Код страны в номере: поле пустое или в нём только код — подставляем новый
                                const typed = prev.phone.trim();
                                const onlyCode =
                                    typed === '' || countries.some((c) => c.phone_code && typed === c.phone_code);
                                const dial = dialOf(id);

                                return { ...prev, country_id: id, phone: dial && onlyCode ? `${dial} ` : prev.phone };
                            });
                            if (errors.country_id) clearErrors('country_id');
                        }}
                        error={errors.country_id}
                    />

                    {byPhone ? (
                        <TextInput
                            label={t('auth.phone_label')}
                            type="tel"
                            inputMode="tel"
                            name="phone"
                            autoComplete="tel"
                            required
                            placeholder={t('auth.phone_placeholder')}
                            value={data.phone}
                            onChange={(e) => {
                                setData('phone', e.target.value);
                                if (errors.phone) clearErrors('phone');
                            }}
                            error={errors.phone}
                            hint={t('auth.reg_phone_hint')}
                        />
                    ) : (
                        <TextInput
                            label={t('auth.reg_email_label')}
                            type="email"
                            autoCapitalize="none"
                            autoCorrect="off"
                            spellCheck={false}
                            name="email"
                            autoComplete="email"
                            required
                            placeholder={t('auth.email_placeholder')}
                            value={data.email}
                            onChange={(e) => {
                                setData('email', e.target.value);
                                if (errors.email) clearErrors('email');
                            }}
                            error={errors.email}
                            hint={t('auth.reg_email_hint')}
                        />
                    )}

                    <Button
                        type="submit"
                        size="lg"
                        block
                        loading={processing}
                        disabled={
                            data.country_id === null ||
                            (byPhone ? data.phone.replace(/\D/g, '').length < 8 : data.email.trim() === '')
                        }
                    >
                        {t('auth.continue')}
                    </Button>
                </form>
            )}

            <p className="text-muted mt-6 text-center text-sm">
                {t('auth.have_account')}{' '}
                <Link href={routes.login} className="text-primary-700 hover:underline">
                    {t('auth.login_link')}
                </Link>
            </p>
        </AuthLayout>
    );
}
