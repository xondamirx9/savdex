import { useForm } from '@inertiajs/react';
import type { FormEvent } from 'react';
import { Alert, Button, PasswordInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';

/**
 * Смена пароля, выданного администратором.
 *
 * Ссылки «пропустить» здесь нет намеренно: пока пароль знают двое,
 * доступ нельзя считать принадлежащим пользователю.
 */
export default function ForcePassword() {
    const { data, setData, post, processing, errors, clearErrors } = useForm({
        password: '',
        password_confirmation: '',
    });

    function update(key: 'password' | 'password_confirmation', value: string) {
        setData((d) => ({ ...d, [key]: value }));
        clearErrors('password', 'password_confirmation');
    }

    function submit(e: FormEvent) {
        e.preventDefault();
        post('/password/change', {
            onFinish: () => setData({ password: '', password_confirmation: '' }),
        });
    }

    return (
        <AuthLayout
            title={t('auth.force_title')}
            heading={t('auth.force_heading')}
            subheading={t('auth.force_subheading')}
        >
            <Alert tone="warning" className="mb-5">
                {t('auth.force_warning')}
            </Alert>

            <form onSubmit={submit} className="space-y-5" noValidate>
                <PasswordInput
                    label={t('auth.new_password_label')}
                    name="password"
                    autoComplete="new-password"
                    required
                    placeholder={t('auth.password_placeholder')}
                    value={data.password}
                    onChange={(e) => update('password', e.target.value)}
                    error={errors.password}
                    autoFocus
                />
                <PasswordInput
                    label={t('auth.password_confirm_label')}
                    name="password_confirmation"
                    autoComplete="new-password"
                    required
                    value={data.password_confirmation}
                    onChange={(e) => update('password_confirmation', e.target.value)}
                    error={errors.password_confirmation}
                />
                <Button type="submit" size="lg" block loading={processing}>
                    {t('auth.save_and_continue')}
                </Button>
            </form>
        </AuthLayout>
    );
}
