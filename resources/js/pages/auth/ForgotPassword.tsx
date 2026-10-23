import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft, Mail, MessageSquare, Send } from 'lucide-react';
import type { FormEvent } from 'react';
import { Alert, Button, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

type Channel = 'mail' | 'sms' | 'telegram' | 'whatsapp';

/**
 * Восстановление пароля в два шага.
 *
 * 1. Почта или телефон.
 * 2. «Если аккаунт с такими данными есть, мы отправили ссылку на почту или
 *    код в SMS» — одинаково для всех, есть такой аккаунт или нет: ни текст,
 *    ни шаг, ни способы «Отправить ещё раз» (включённые на сайте, а не у
 *    аккаунта) его не выдают. Куда ушло — решает сервер: способом, которым
 *    искали, если он есть у аккаунта. Код из SMS вводится здесь же и ведёт
 *    на ту же страницу нового пароля, что и ссылка.
 *
 * Присылается ссылка или код, а не пароль: паролей площадка не хранит.
 */
export default function ForgotPassword({
    status,
    step = 'find',
    channels = [],
}: {
    status?: string | null;
    step?: 'find' | 'sent';
    /** Способы «Отправить ещё раз», включённые на сайте */
    channels?: Channel[];
}) {
    return (
        <AuthLayout
            title={t('auth.forgot_title')}
            heading={t(step === 'sent' ? 'auth.forgot_sent_heading' : 'auth.forgot_heading')}
            subheading={step === 'find' ? t('auth.forgot_subheading') : undefined}
        >
            {step === 'sent' ? <SentStep status={status} channels={channels} /> : <FindStep status={status} />}

            <p className="text-muted mt-6 text-center text-sm">
                <Link href={routes.login} className="text-primary-700 inline-flex items-center gap-1.5 hover:underline">
                    <ArrowLeft aria-hidden className="size-4" />
                    {t('auth.back_to_login')}
                </Link>
            </p>
        </AuthLayout>
    );
}

/** Шаг 1: почта или телефон. Ответ не выдаёт, есть ли такой аккаунт. */
function FindStep({ status }: { status?: string | null }) {
    const { data, setData, post, processing, errors, clearErrors } = useForm({ login: '' });

    function submit(e: FormEvent) {
        e.preventDefault();
        post('/forgot-password/find', { preserveScroll: true });
    }

    return (
        <form onSubmit={submit} className="space-y-5" noValidate>
            {status && (
                <div className="space-y-3">
                    <Alert tone="success">{status}</Alert>
                    <p className="text-muted text-sm leading-relaxed">{t('auth.forgot_sent_hint')}</p>
                </div>
            )}

            <TextInput
                label={t('auth.forgot_login_label')}
                type="text"
                inputMode="email"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                name="login"
                autoComplete="username"
                required
                value={data.login}
                onChange={(e) => {
                    setData('login', e.target.value);
                    if (errors.login) clearErrors('login');
                }}
                error={errors.login}
                hint={t('auth.forgot_login_hint')}
                autoFocus
            />
            <Button type="submit" size="lg" block loading={processing} disabled={data.login.trim() === ''}>
                {t('auth.forgot_continue')}
            </Button>
        </form>
    );
}

const ICONS = { mail: Mail, sms: MessageSquare, telegram: Send, whatsapp: MessageSquare };

/** Шаг 2: отправили (если аккаунт есть) — код из SMS, «Отправить ещё раз», «Другой аккаунт». */
function SentStep({ status, channels }: { status?: string | null; channels: Channel[] }) {
    const code = useForm({ sms_code: '' });
    const resend = useForm<{ channel: Channel | '' }>({ channel: '' });
    const restart = useForm({});

    function confirm(e: FormEvent) {
        e.preventDefault();
        code.post('/forgot-password/sms/confirm', { preserveScroll: true });
    }

    function sendAgain(channel: Channel) {
        const options = { preserveScroll: true, onSuccess: () => code.reset() };

        // SMS — свой адрес: у него своя, более редкая частота
        if (channel === 'sms') {
            resend.transform(() => ({}));
            resend.post('/forgot-password/sms/resend', options);
        } else {
            resend.transform(() => ({ channel }));
            resend.post('/forgot-password/send', options);
        }
    }

    return (
        <div className="space-y-5">
            {status && (
                <div className="space-y-3">
                    <Alert tone="success">{status}</Alert>
                    <p className="text-muted text-sm leading-relaxed">{t('auth.forgot_sent_hint')}</p>
                </div>
            )}

            {channels.includes('sms') && (
                <form onSubmit={confirm} className="space-y-4" noValidate>
                    <TextInput
                        label={t('auth.forgot_code_label')}
                        name="sms_code"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={10}
                        required
                        value={code.data.sms_code}
                        onChange={(e) => {
                            code.setData('sms_code', e.target.value.replace(/\D/g, ''));
                            if (code.errors.sms_code) code.clearErrors('sms_code');
                        }}
                        error={code.errors.sms_code}
                    />
                    <Button type="submit" size="lg" block loading={code.processing} disabled={code.data.sms_code.length < 4}>
                        {t('auth.continue')}
                    </Button>
                </form>
            )}

            <div className="space-y-2">
                <p className="text-muted text-sm">{t('auth.forgot_resend_title')}</p>
                {channels.map((channel) => {
                    const Icon = ICONS[channel];

                    return (
                        <button
                            key={channel}
                            type="button"
                            disabled={resend.processing}
                            onClick={() => sendAgain(channel)}
                            className="rounded-card border-border hover:border-primary-700 hover:bg-primary-50 flex w-full items-center gap-3.5 border p-3.5 text-left transition-colors disabled:opacity-60"
                        >
                            <Icon aria-hidden className="text-primary-700 size-5 shrink-0" />
                            <b>{t(`auth.forgot_via_${channel}`)}</b>
                        </button>
                    );
                })}
            </div>

            <Button
                type="button"
                variant="ghost"
                size="lg"
                block
                loading={restart.processing}
                onClick={() => restart.post('/forgot-password/restart')}
            >
                {t('auth.forgot_other_account')}
            </Button>
        </div>
    );
}
