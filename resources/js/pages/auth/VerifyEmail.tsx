import { useForm, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { MailCheck, RefreshCw, ShieldCheck } from 'lucide-react';
import type { FormEvent } from 'react';
import { Alert, Button, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
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
            title="Подтвердите почту"
            heading="Подтвердите почту"
            subheading="Остался один шаг — и кабинет открыт полностью."
        >
            <div className="space-y-5">
                <div className="bg-primary-50 rounded-card flex gap-3.5 p-4">
                    <MailCheck aria-hidden className="text-primary-700 mt-0.5 size-6 shrink-0" />
                    <div className="text-sm leading-relaxed">
                        Письмо с кодом подтверждения отправлено на{' '}
                        <b className="break-all">{email ?? auth?.user?.email}</b>. Введите код из письма ниже
                        или нажмите кнопку внутри письма.
                    </div>
                </div>

                {status && <Alert tone="success">{status}</Alert>}

                <form onSubmit={confirm} className="space-y-4" noValidate>
                    <TextInput
                        label="Код из письма"
                        name="code"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        placeholder="000000"
                        required
                        value={codeForm.data.code}
                        onChange={(e) => codeForm.setData('code', e.target.value.replace(/\D/g, ''))}
                        error={codeForm.errors.code}
                        hint="Шесть цифр, код действует 15 минут"
                    />
                    <Button type="submit" size="lg" block loading={codeForm.processing}>
                        <ShieldCheck aria-hidden className="size-4" />
                        Подтвердить почту
                    </Button>
                </form>

                <div className="text-muted space-y-2 text-sm leading-relaxed">
                    <p>
                        Письма нет? Проверьте папку «Спам» — туда попадает почти половина писем от новых
                        отправителей.
                    </p>
                    <p>Адрес указан с опечаткой? Смените его в настройках — письмо уйдёт заново.</p>
                </div>

                <form onSubmit={resend}>
                    <Button type="submit" variant="secondary" size="lg" block loading={processing}>
                        <RefreshCw aria-hidden className="size-4" />
                        Отправить письмо повторно
                    </Button>
                </form>

                {/* Кабинет доступен и без подтверждения — закрыта только публикация.
                    Держать человека на этом экране силой значит терять его совсем. */}
                <Link href={routes.cabinet} className="btn btn-secondary btn-lg btn-block">
                    Перейти в кабинет
                </Link>

                <p className="text-muted pt-1 text-center text-sm">
                    Это не ваш адрес?{' '}
                    <button
                        type="button"
                        className="text-primary-700 hover:underline"
                        onClick={() => logout.post(routes.logout)}
                    >
                        Выйти
                    </button>
                </p>
            </div>
        </AuthLayout>
    );
}
