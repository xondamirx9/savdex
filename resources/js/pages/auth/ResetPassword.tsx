import { useForm } from '@inertiajs/react';
import type { FormEvent } from 'react';
import { Button, PasswordInput, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';

export default function ResetPassword({ token, email }: { token: string; email: string }) {
    const { data, setData, post, processing, errors } = useForm({
        token,
        email,
        password: '',
        password_confirmation: '',
    });

    function submit(e: FormEvent) {
        e.preventDefault();
        post('/reset-password', {
            onFinish: () => setData((d) => ({ ...d, password: '', password_confirmation: '' })),
        });
    }

    return (
        <AuthLayout
            title={t('auth.reset_title')}
            heading={t('auth.reset_heading')}
            subheading={t('auth.reset_subheading')}
        >
            <form onSubmit={submit} className="space-y-5" noValidate>
                <TextInput
                    label={t('auth.email_short_label')}
                    type="email"
                    name="email"
                    autoComplete="email"
                    required
                    value={data.email}
                    onChange={(e) => setData('email', e.target.value)}
                    error={errors.email}
                />
                <PasswordInput
                    label={t('auth.new_password_label')}
                    name="password"
                    autoComplete="new-password"
                    required
                    placeholder={t('auth.password_placeholder')}
                    value={data.password}
                    onChange={(e) => setData('password', e.target.value)}
                    error={errors.password}
                    autoFocus
                />
                <PasswordInput
                    label={t('auth.password_confirm_label')}
                    name="password_confirmation"
                    autoComplete="new-password"
                    required
                    value={data.password_confirmation}
                    onChange={(e) => setData('password_confirmation', e.target.value)}
                    error={errors.password_confirmation}
                />
                <Button type="submit" size="lg" block loading={processing}>
                    {t('auth.save_password')}
                </Button>
            </form>
        </AuthLayout>
    );
}
