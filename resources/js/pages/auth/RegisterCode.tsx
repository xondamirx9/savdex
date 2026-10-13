import { useForm } from '@inertiajs/react';
import { MailCheck, MessageSquare, RefreshCw } from 'lucide-react';
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
    chinaMailbox = false,
    sender = '',
    canSkip = false,
    sms,
}: {
    email: string;
    status?: string | null;
    demoCode?: string | null;
    /** Ящик у китайского почтовика (qq.com, 163.com…) — своя подсказка */
    chinaMailbox?: boolean;
    /** Адрес отправителя — для белого списка почты */
    sender?: string;
    /** Страна с галочкой «Регистрация без кода» — можно продолжить без кода */
    canSkip?: boolean;
    /** Код по SMS (Telnyx): включён ли, на какой номер уже ушёл, код страны */
    sms?: { enabled: boolean; sentTo: string | null; dialCode: string | null };
}) {
    const form = useForm({ code: demoCode ?? '' });
    const resend = useForm({});
    const skip = useForm({});
    const smsSend = useForm({ phone: sms?.sentTo ?? (sms?.dialCode ? `${sms.dialCode} ` : '') });
    const smsCheck = useForm({ sms_code: '' });

    function sendSms(e: FormEvent) {
        e.preventDefault();
        smsSend.post(routes.registerSms, { preserveScroll: true });
    }

    function checkSms(e: FormEvent) {
        e.preventDefault();
        smsCheck.post(routes.registerSmsConfirm, { preserveScroll: true });
    }

    function submit(e: FormEvent) {
        e.preventDefault();
        form.post(routes.registerCode, { preserveScroll: true });
    }

    function sendAgain(e: FormEvent) {
        e.preventDefault();
        resend.post(routes.registerCodeResend, { preserveScroll: true, onSuccess: () => form.reset() });
    }

    function skipCode(e: FormEvent) {
        e.preventDefault();
        skip.post(routes.registerCodeSkip);
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

                {/* qq.com, 163.com: письма идут дольше и уходят в «垃圾邮件» —
                    без этой подсказки китайские клиенты бросали регистрацию */}
                {chinaMailbox && <Alert tone="info">{t('auth.reg_code_cn_hint', { sender })}</Alert>}

                <form onSubmit={sendAgain}>
                    <Button type="submit" variant="secondary" size="lg" block loading={resend.processing}>
                        <RefreshCw aria-hidden className="size-4" />
                        {t('auth.reg_code_resend')}
                    </Button>
                </form>

                {/* Код по SMS: письмо не пришло (китайские ящики режут письма) —
                    номер подтверждается кодом, и учётка полноценная */}
                {sms?.enabled && (
                    <div className="rounded-card border-border space-y-4 border p-4">
                        <div className="flex gap-3">
                            <MessageSquare aria-hidden className="text-primary-700 mt-0.5 size-5 shrink-0" />
                            <div className="text-sm leading-relaxed">
                                <b>{t('auth.reg_sms_title')}</b>
                                <p className="text-muted">{t('auth.reg_sms_hint')}</p>
                            </div>
                        </div>

                        <form onSubmit={sendSms} className="space-y-3" noValidate>
                            <TextInput
                                label={t('auth.phone_label')}
                                name="phone"
                                type="tel"
                                inputMode="tel"
                                autoComplete="tel"
                                value={smsSend.data.phone}
                                onChange={(e) => {
                                    smsSend.setData('phone', e.target.value);
                                    if (smsSend.errors.phone) smsSend.clearErrors('phone');
                                }}
                                error={smsSend.errors.phone}
                            />
                            <Button type="submit" variant="secondary" size="lg" block loading={smsSend.processing}>
                                {sms.sentTo ? t('auth.reg_sms_resend') : t('auth.reg_sms_send')}
                            </Button>
                        </form>

                        {sms.sentTo && (
                            <form onSubmit={checkSms} className="space-y-3" noValidate>
                                <TextInput
                                    label={t('auth.reg_sms_code_label', { phone: sms.sentTo })}
                                    name="sms_code"
                                    inputMode="numeric"
                                    autoComplete="one-time-code"
                                    maxLength={10}
                                    value={smsCheck.data.sms_code}
                                    onChange={(e) => {
                                        smsCheck.setData('sms_code', e.target.value.replace(/\D/g, ''));
                                        if (smsCheck.errors.sms_code) smsCheck.clearErrors('sms_code');
                                    }}
                                    error={smsCheck.errors.sms_code}
                                />
                                <Button
                                    type="submit"
                                    size="lg"
                                    block
                                    loading={smsCheck.processing}
                                    disabled={smsCheck.data.sms_code.length < 4}
                                >
                                    {t('auth.continue')}
                                </Button>
                            </form>
                        )}
                    </div>
                )}

                {/* Письмо не дошло (китайские ящики) — можно и без кода: учётка
                    будет с пометкой «Не подтверждено», пока почту не подтвердят */}
                {canSkip && (
                    <form onSubmit={skipCode} className="space-y-2">
                        <Button type="submit" variant="ghost" size="lg" block loading={skip.processing}>
                            {t('auth.reg_code_skip')}
                        </Button>
                        <p className="text-muted text-center text-xs leading-relaxed">{t('auth.reg_code_skip_hint')}</p>
                    </form>
                )}
            </div>
        </AuthLayout>
    );
}
