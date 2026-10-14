import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { Alert, Button, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

type Channel = 'mail' | 'telegram' | 'whatsapp' | 'sms';

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
 *
 * SMS — для подтверждённого номера (регистрация по телефону): код из SMS
 * ведёт на ту же страницу нового пароля, что и ссылка из письма.
 */
export default function ForgotPassword({
    status,
    channels = ['mail'],
    sms,
}: {
    status?: string;
    channels?: Channel[];
    sms?: { available: boolean; sentTo: string | null };
}) {
    const all: Channel[] = sms?.available ? [...channels, 'sms'] : channels;
    const { data, setData, post, processing, errors } = useForm<{
        email: string;
        channel: Channel;
        phone: string;
    }>({
        email: '',
        channel: sms?.sentTo ? 'sms' : 'mail',
        phone: sms?.sentTo ?? '',
    });
    const code = useForm({ sms_code: '' });
    // «Изменить номер»: снова поле номера, хотя код уже уходил
    const [changing, setChanging] = useState(false);
    const bySms = data.channel === 'sms';

    function submit(e: FormEvent) {
        e.preventDefault();
        post(bySms ? '/forgot-password/sms' : '/forgot-password', {
            preserveScroll: true,
            onSuccess: () => setChanging(false),
        });
    }

    function confirm(e: FormEvent) {
        e.preventDefault();
        code.post('/forgot-password/sms/confirm', { preserveScroll: true });
    }

    if (bySms && sms?.sentTo && !changing) {
        return (
            <AuthLayout title={t('auth.forgot_title')} heading={t('auth.forgot_sms_heading')}>
                <form onSubmit={confirm} className="space-y-5" noValidate>
                    {status && <Alert tone="success">{status}</Alert>}
                    <TextInput
                        label={t('auth.reg_sms_code_label', { phone: sms.sentTo })}
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
                    <Button
                        type="submit"
                        size="lg"
                        block
                        loading={code.processing}
                        disabled={code.data.sms_code.length < 4}
                    >
                        {t('auth.continue')}
                    </Button>
                    <Button type="button" size="lg" block variant="ghost" onClick={() => setChanging(true)}>
                        {t('auth.reg_sms_change')}
                    </Button>
                </form>
            </AuthLayout>
        );
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
            {status && !bySms ? (
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
                    {all.length > 1 && (
                        <div>
                            <span className="label">{t('auth.forgot_channel')}</span>
                            <div className="row wrap mt-8" style={{ gap: 6 }}>
                                {all.map((channel) => (
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

                    {bySms ? (
                        <TextInput
                            label={t('auth.phone_label')}
                            type="tel"
                            inputMode="tel"
                            name="phone"
                            autoComplete="tel"
                            required
                            placeholder={t('auth.phone_placeholder')}
                            value={data.phone}
                            onChange={(e) => setData('phone', e.target.value)}
                            error={(errors as Record<string, string | undefined>).phone}
                            hint={t('auth.forgot_sms_hint')}
                            autoFocus
                        />
                    ) : (
                        <TextInput
                            label={t('auth.email_label')}
                            type="email"
                            autoCapitalize="none"
                            autoCorrect="off"
                            spellCheck={false}
                            name="email"
                            autoComplete="email"
                            required
                            placeholder={t('auth.email_placeholder')}
                            value={data.email}
                            onChange={(e) => setData('email', e.target.value)}
                            error={errors.email}
                            autoFocus
                        />
                    )}
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
