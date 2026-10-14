import { useForm } from '@inertiajs/react';
import { type FormEvent, useState } from 'react';
import { RegisterSteps } from '@/components/auth/RegisterSteps';
import { CountryField } from '@/components/CountryField';
import { Button, TextInput } from '@/components/ui';
import { Link } from '@/components/ui/Link';
import { AuthLayout } from '@/layouts/AuthLayout';
import type { CountryOption } from '@/lib/countries';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Регистрация, шаг 1 из 3: страна и способ — почта или телефон.
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
    method: initialMethod = 'email',
    phone = null,
}: {
    email?: string | null;
    countryId?: number | null;
    countries?: CountryOption[];
    /** Код по SMS настроен (Telnyx) — есть вкладка «Телефон» */
    phoneAvailable?: boolean;
    method?: 'email' | 'phone';
    /** Номер, на который код уже уходил («Изменить номер» со второго шага) */
    phone?: string | null;
}) {
    const [method, setMethod] = useState<'email' | 'phone'>(phoneAvailable ? initialMethod : 'email');
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
            heading={t(byPhone ? 'auth.reg_phone_heading' : 'auth.reg_email_heading')}
            subheading={t(byPhone ? 'auth.reg_phone_subheading' : 'auth.reg_email_subheading')}
        >
            <RegisterSteps current={1} />

            {phoneAvailable && (
                <div
                    role="tablist"
                    className="tabs"
                    aria-label={t('auth.reg_method_label')}
                    style={{ marginBottom: 20 }}
                >
                    {(['email', 'phone'] as const).map((key) => (
                        <button
                            key={key}
                            type="button"
                            role="tab"
                            className="tab"
                            aria-selected={method === key}
                            tabIndex={method === key ? 0 : -1}
                            onClick={() => {
                                setMethod(key);
                                clearErrors();
                            }}
                        >
                            {t(key === 'email' ? 'auth.reg_method_email' : 'auth.reg_method_phone')}
                        </button>
                    ))}
                </div>
            )}

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

            <p className="text-muted mt-6 text-center text-sm">
                {t('auth.have_account')}{' '}
                <Link href={routes.login} className="text-primary-700 hover:underline">
                    {t('auth.login_link')}
                </Link>
            </p>
        </AuthLayout>
    );
}
