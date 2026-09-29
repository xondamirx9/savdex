import { useForm } from '@inertiajs/react';
import type { FormEvent } from 'react';
import { RegisterSteps } from '@/components/auth/RegisterSteps';
import { Button, TextInput } from '@/components/ui';
import { Link } from '@/components/ui/Link';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Регистрация, шаг 1 из 3: только почта.
 * «Продолжить» отправляет на адрес код и ведёт на второй шаг.
 */
export default function RegisterEmail({ email }: { email?: string | null }) {
    const { data, setData, post, processing, errors, clearErrors } = useForm({ email: email ?? '' });

    function submit(e: FormEvent) {
        e.preventDefault();
        post(routes.registerEmail);
    }

    return (
        <AuthLayout
            title={t('auth.register_title')}
            heading={t('auth.reg_email_heading')}
            subheading={t('auth.reg_email_subheading')}
        >
            <RegisterSteps current={1} />

            <form onSubmit={submit} className="space-y-5" noValidate>
                <TextInput
                    label={t('auth.reg_email_label')}
                    type="email"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    name="email"
                    autoComplete="email"
                    required
                    autoFocus
                    placeholder={t('auth.email_placeholder')}
                    value={data.email}
                    onChange={(e) => {
                        setData('email', e.target.value);
                        if (errors.email) clearErrors('email');
                    }}
                    error={errors.email}
                    hint={t('auth.reg_email_hint')}
                />

                <Button type="submit" size="lg" block loading={processing} disabled={data.email.trim() === ''}>
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
