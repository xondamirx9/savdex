import { useForm } from '@inertiajs/react';
import { MailCheck, RefreshCw } from 'lucide-react';
import type { FormEvent } from 'react';
import { RegisterSteps } from '@/components/auth/RegisterSteps';
import { Alert, Button, TextInput } from '@/components/ui';
import { Link } from '@/components/ui/Link';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Регистрация, шаг 2 из 3: код из письма.
 * Верный код открывает третий шаг — анкету.
 */
export default function RegisterCode({
    email,
    status,
    demoCode,
}: {
    email: string;
    status?: string | null;
    demoCode?: string | null;
}) {
    const form = useForm({ code: demoCode ?? '' });
    const resend = useForm({});

    function submit(e: FormEvent) {
        e.preventDefault();
        form.post(routes.registerCode, { preserveScroll: true });
    }

    function sendAgain(e: FormEvent) {
        e.preventDefault();
        resend.post(routes.registerCodeResend, { preserveScroll: true, onSuccess: () => form.reset() });
    }

    return (
        <AuthLayout title={t('auth.register_title')} heading={t('auth.reg_code_heading')}>
            <RegisterSteps current={2} />

            <div className="space-y-5">
                <div className="bg-primary-50 rounded-card flex gap-3.5 p-4">
                    <MailCheck aria-hidden className="text-primary-700 mt-0.5 size-6 shrink-0" />
                    <div className="text-sm leading-relaxed">
                        {t('auth.reg_code_sent')} <b className="break-all">{email}</b>.{' '}
                        <Link href={routes.register} className="text-primary-700 hover:underline">
                            {t('auth.reg_code_change')}
                        </Link>
                    </div>
                </div>

                {status && <Alert tone="success">{status}</Alert>}
                {demoCode && <Alert tone="info">{t('auth.reg_demo_code', { code: demoCode })}</Alert>}

                <form onSubmit={submit} className="space-y-4" noValidate>
                    <TextInput
                        label={t('auth.code_label')}
                        name="code"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        autoFocus
                        placeholder={t('auth.code_placeholder')}
                        required
                        value={form.data.code}
                        onChange={(e) => {
                            form.setData('code', e.target.value.replace(/\D/g, ''));
                            if (form.errors.code) form.clearErrors('code');
                        }}
                        error={form.errors.code}
                        hint={t('auth.code_hint')}
                    />
                    <Button
                        type="submit"
                        size="lg"
                        block
                        loading={form.processing}
                        disabled={form.data.code.length !== 6}
                    >
                        {t('auth.continue')}
                    </Button>
                </form>

                <p className="text-muted text-sm leading-relaxed">{t('auth.verify_spam_hint')}</p>

                <form onSubmit={sendAgain}>
                    <Button type="submit" variant="secondary" size="lg" block loading={resend.processing}>
                        <RefreshCw aria-hidden className="size-4" />
                        {t('auth.reg_code_resend')}
                    </Button>
                </form>
            </div>
        </AuthLayout>
    );
}
