import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft } from 'lucide-react';
import type { FormEvent } from 'react';
import { Alert, Button, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

type Channel = 'mail' | 'telegram' | 'whatsapp';

/**
 * Восстановление пароля.
 *
 * Ссылку можно получить не только на почту: тот, кто потерял доступ
 * к рабочему ящику, выбирает Telegram или WhatsApp. Выбор появляется
 * только если площадка эти способы умеет — список приходит с сервера.
 *
 * Присылается именно ссылка, а не пароль: паролей площадка не хранит
 * даже у себя, а тот, что отправлен сообщением, остался бы
 * в переписке навсегда.
 */
export default function ForgotPassword({ status, channels = ['mail'] }: { status?: string; channels?: Channel[] }) {
    const { data, setData, post, processing, errors } = useForm<{ email: string; channel: Channel }>({
        email: '',
        channel: 'mail',
    });

    function submit(e: FormEvent) {
        e.preventDefault();
        post('/forgot-password', { preserveScroll: true });
    }

    const hint =
        data.channel === 'telegram'
            ? t('auth.channel_telegram_hint')
            : data.channel === 'whatsapp'
              ? t('auth.channel_whatsapp_hint')
              : null;

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
                    {/* Переключатель показывается, только когда способов
                        больше одного: строка с единственной кнопкой
                        ничего не объясняет, а место занимает */}
                    {channels.length > 1 && (
                        <div>
                            <span className="label">{t('auth.forgot_channel')}</span>
                            <div className="row wrap mt-8" style={{ gap: 6 }}>
                                {channels.map((channel) => (
                                    <button
                                        key={channel}
                                        type="button"
                                        className={cn('chip', data.channel === channel && 'chip-active')}
                                        aria-pressed={data.channel === channel}
                                        onClick={() => setData('channel', channel)}
                                    >
                                        {t(`auth.channel_${channel}`)}
                                    </button>
                                ))}
                            </div>
                            {hint && <p className="text-muted mt-8 text-sm leading-relaxed">{hint}</p>}
                        </div>
                    )}

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
