import { useForm } from '@inertiajs/react';
import { useState, type FormEvent } from 'react';
import { CaptchaField } from '@/components/auth/CaptchaField';
import { RegisterSteps } from '@/components/auth/RegisterSteps';
import { CountryField } from '@/components/CountryField';
import { Button, TextInput } from '@/components/ui';
import { Link } from '@/components/ui/Link';
import { AuthLayout } from '@/layouts/AuthLayout';
import type { CountryOption } from '@/lib/countries';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Регистрация, шаг 1 из 3: страна и почта.
 * «Продолжить» отправляет на адрес код и ведёт на второй шаг. Для стран
 * с галочкой «Регистрация без кода» там можно продолжить без кода.
 */
export default function RegisterEmail({
    email,
    countryId = null,
    countries = [],
    captcha = false,
}: {
    email?: string | null;
    countryId?: number | null;
    countries?: CountryOption[];
    captcha?: boolean;
}) {
    const { data, setData, post, processing, errors, clearErrors } = useForm<{
        email: string;
        country_id: number | null;
        captcha: string;
    }>({ email: email ?? '', country_id: countryId, captcha: '' });
    // Задание капчи одноразовое: после каждой отправки — новое
    const [captchaKey, setCaptchaKey] = useState(0);

    function submit(e: FormEvent) {
        e.preventDefault();
        post(routes.registerEmail, { onFinish: () => setCaptchaKey((k) => k + 1) });
    }

    return (
        <AuthLayout
            title={t('auth.register_title')}
            heading={t('auth.reg_email_heading')}
            subheading={t('auth.reg_email_subheading')}
        >
            <RegisterSteps current={1} />

            <form onSubmit={submit} className="space-y-5" noValidate>
                <CountryField
                    id="register-country"
                    countries={countries}
                    value={data.country_id}
                    onChange={(id) => {
                        setData('country_id', id);
                        if (errors.country_id) clearErrors('country_id');
                    }}
                    error={errors.country_id}
                />

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

                {captcha && (
                    <CaptchaField
                        purpose="register"
                        value={data.captcha}
                        onChange={(text) => {
                            setData('captcha', text);
                            if (errors.captcha && text !== '') clearErrors('captcha');
                        }}
                        error={errors.captcha}
                        reloadKey={captchaKey}
                    />
                )}

                <Button
                    type="submit"
                    size="lg"
                    block
                    loading={processing}
                    disabled={data.email.trim() === '' || data.country_id === null}
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
