import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft, Mail, MessageSquare, RefreshCw, Send } from 'lucide-react';
import type { FormEvent } from 'react';
import { Alert, Button, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

type Channel = 'mail' | 'sms' | 'telegram' | 'whatsapp';

/**
 * Восстановление пароля в три шага.
 *
 * 1. Почта или телефон — сайт находит аккаунт.
 * 2. Куда прислать — решает аккаунт: почта не подтверждена, а телефон да —
 *    только SMS; телефон не подтверждён — только почта; подтверждены оба —
 *    человек выбирает сам (этот шаг виден только тогда).
 * 3. Почта — ссылка в письме; SMS — код здесь же, он ведёт на ту же
 *    страницу нового пароля.
 *
 * Присылается ссылка или код, а не пароль: паролей площадка не хранит.
 */
export default function ForgotPassword({
    status,
    step = 'find',
    sentTo = null,
    options = [],
}: {
    status?: string | null;
    step?: 'find' | 'choose' | 'code';
    /** Номер, на который ушёл код (скрыт: +998•••4567) */
    sentTo?: string | null;
    /** Способы этого аккаунта, когда подтверждены и почта, и телефон */
    options?: { channel: Channel; to: string }[];
}) {
    return (
        <AuthLayout
            title={t('auth.forgot_title')}
            heading={t(
                step === 'code'
                    ? 'auth.forgot_sms_heading'
                    : step === 'choose'
                      ? 'auth.forgot_choose_heading'
                      : 'auth.forgot_heading',
            )}
            subheading={step === 'find' ? t('auth.forgot_subheading') : undefined}
        >
            {step === 'code' && sentTo ? (
                <CodeStep sentTo={sentTo} status={status} />
            ) : step === 'choose' ? (
                <ChooseStep options={options} />
            ) : (
                <FindStep status={status} />
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

/** Шаг 2: подтверждены и почта, и телефон — куда прислать, выбирает человек. */
function ChooseStep({ options }: { options: { channel: Channel; to: string }[] }) {
    const send = useForm<{ channel: Channel | '' }>({ channel: '' });
    const restart = useForm({});

    function choose(channel: Channel) {
        send.transform(() => ({ channel }));
        send.post('/forgot-password/send', { preserveScroll: true });
    }

    return (
        <div className="space-y-3">
            {options.map(({ channel, to }) => {
                const Icon = ICONS[channel];

                return (
                    <button
                        key={channel}
                        type="button"
                        disabled={send.processing}
                        onClick={() => choose(channel)}
                        className="rounded-card border-border hover:border-primary-700 hover:bg-primary-50 flex w-full items-center gap-3.5 border p-4 text-left transition-colors disabled:opacity-60"
                    >
                        <Icon aria-hidden className="text-primary-700 size-6 shrink-0" />
                        <span className="min-w-0">
                            <b className="block">{t(`auth.forgot_via_${channel}`)}</b>
                            {to && <span className="text-muted block text-sm break-all">{to}</span>}
                        </span>
                    </button>
                );
            })}

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

/** Шаг 3 по SMS: код, «Отправить SMS ещё раз», «Другой аккаунт». */
function CodeStep({ sentTo, status }: { sentTo: string; status?: string | null }) {
    const code = useForm({ sms_code: '' });
    const resend = useForm({});
    const restart = useForm({});

    function confirm(e: FormEvent) {
        e.preventDefault();
        code.post('/forgot-password/sms/confirm', { preserveScroll: true });
    }

    function sendAgain(e: FormEvent) {
        e.preventDefault();
        resend.post('/forgot-password/sms/resend', { preserveScroll: true, onSuccess: () => code.reset() });
    }

    return (
        <div className="space-y-5">
            {status && <Alert tone="success">{status}</Alert>}

            <form onSubmit={confirm} className="space-y-4" noValidate>
                <TextInput
                    label={t('auth.reg_sms_code_label', { phone: sentTo })}
                    name="sms_code"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={10}
                    autoFocus
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

            <form onSubmit={sendAgain}>
                <Button type="submit" variant="secondary" size="lg" block loading={resend.processing}>
                    <RefreshCw aria-hidden className="size-4" />
                    {t('auth.reg_sms_resend')}
                </Button>
            </form>

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
