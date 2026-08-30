import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft } from 'lucide-react';
import type { FormEvent } from 'react';
import { Alert, Button, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

export default function ForgotPassword({ status }: { status?: string }) {
    const { data, setData, post, processing, errors } = useForm({ email: '' });

    function submit(e: FormEvent) {
        e.preventDefault();
        post('/forgot-password', { preserveScroll: true });
    }

    return (
        <AuthLayout
            title={t('auth.forgot_title')}
            heading={t('auth.forgot_heading')}
            subheading={t('auth.forgot_subheading')}
        >
            {/*
             * Ответ сервера одинаков и для существующего адреса, и для
             * несуществующего. Иначе форма превращается в способ узнать,
             * зарегистрирована ли на площадке конкретная компания.
             */}
            {status ? (
                <div className="space-y-5">
                    <Alert tone="success">{status}</Alert>
                    <p className="text-muted text-sm leading-relaxed">
                        {t('auth.forgot_sent_hint')}
                    </p>
                    <Button type="button" size="lg" block variant="secondary" onClick={() => post('/forgot-password')}>
                        {t('auth.forgot_resend')}
                    </Button>
                </div>
            ) : (
                <form onSubmit={submit} className="space-y-5" noValidate>
                    <TextInput
                        label={t('auth.email_label')}
                        type="email"
                        name="email"
                        autoComplete="email"
                        required
                        placeholder={t('auth.email_placeholder')}
                        value={data.email}
                        onChange={(e) => setData('email', e.target.value)}
                        error={errors.email}
                        autoFocus
                    />
                    <Button type="submit" size="lg" block loading={processing}>
                        {t('auth.forgot_send')}
                    </Button>
                </form>
            )}

            <p className="text-muted mt-6 text-center text-sm">
                <Link href={routes.login} className="text-primary-700 inline-flex items-center gap-1.5 hover:underline">
                    <ArrowLeft aria-hidden className="size-4" />
                    {t('auth.back_to_login')}
                </Link>
            </p>
        </AuthLayout>
    );
}
