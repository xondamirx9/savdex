import { useForm, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { MailCheck, RefreshCw, ShieldCheck } from 'lucide-react';
import type { FormEvent } from 'react';
import { Alert, Button, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

/**
 * Экран после регистрации.
 *
 * Раньше здесь была заглушка, и человек упирался в тупик: аккаунт создан,
 * письмо ушло, а на экране пусто — ни объяснения, ни повторной отправки,
 * ни выхода. Самая дорогая точка отвала во всей воронке: пользователь
 * уже потратил силы на форму и теряется на последнем шаге.
 *
 * Основной путь — код из письма: ссылка из письма открывается в браузере
 * почты без сессии, а код вводится там, где человек регистрировался.
 * Кнопка в письме остаётся как запасной путь.
 */
export default function VerifyEmail({ email, status }: { email: string; status?: string }) {
    const { auth } = usePage<SharedProps>().props;
    const { post, processing } = useForm({});
    const logout = useForm({});
    const codeForm = useForm({ code: '' });

    function resend(e: FormEvent) {
        e.preventDefault();
        post(routes.verifyResend, { preserveScroll: true });
    }

    function confirm(e: FormEvent) {
        e.preventDefault();
        codeForm.post(routes.verifyCode, { preserveScroll: true });
    }

    return (
        <AuthLayout
            title={t('auth.verify_title')}
            heading={t('auth.verify_title')}
            subheading={t('auth.verify_subheading')}
        >
            <div className="space-y-5">
                <div className="bg-primary-50 rounded-card flex gap-3.5 p-4">
                    <MailCheck aria-hidden className="text-primary-700 mt-0.5 size-6 shrink-0" />
                    <div className="text-sm leading-relaxed">
                        {t('auth.verify_sent_to')}{' '}
                        <b className="break-all">{email ?? auth?.user?.email}</b>. {t('auth.verify_enter_code')}
                    </div>
                </div>

                {status && <Alert tone="success">{status}</Alert>}

                <form onSubmit={confirm} className="space-y-4" noValidate>
                    <TextInput
                        label={t('auth.code_label')}
                        name="code"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        placeholder={t('auth.code_placeholder')}
                        required
                        value={codeForm.data.code}
                        onChange={(e) => codeForm.setData('code', e.target.value.replace(/\D/g, ''))}
                        error={codeForm.errors.code}
                        hint={t('auth.code_hint')}
                    />
                    <Button type="submit" size="lg" block loading={codeForm.processing}>
                        <ShieldCheck aria-hidden className="size-4" />
                        {t('auth.verify_button')}
                    </Button>
                </form>

                <div className="text-muted space-y-2 text-sm leading-relaxed">
                    <p>{t('auth.verify_spam_hint')}</p>
                    <p>{t('auth.verify_typo_hint')}</p>
                </div>

                <form onSubmit={resend}>
                    <Button type="submit" variant="secondary" size="lg" block loading={processing}>
                        <RefreshCw aria-hidden className="size-4" />
                        {t('auth.verify_resend')}
                    </Button>
                </form>

                {/* Кабинет доступен и без подтверждения — закрыта только публикация.
                    Держать человека на этом экране силой значит терять его совсем. */}
                <Link href={routes.cabinet} className="btn btn-secondary btn-lg btn-block">
                    {t('auth.go_to_cabinet')}
                </Link>

                <p className="text-muted pt-1 text-center text-sm">
                    {t('auth.not_your_email')}{' '}
                    <button
                        type="button"
                        className="text-primary-700 hover:underline"
                        onClick={() => logout.post(routes.logout)}
                    >
                        {t('auth.logout')}
                    </button>
                </p>
            </div>
        </AuthLayout>
    );
}
