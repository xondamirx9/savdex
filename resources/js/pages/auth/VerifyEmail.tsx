import { useForm, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { MailCheck, RefreshCw } from 'lucide-react';
import type { FormEvent } from 'react';
import { Alert, Button } from '@/components/ui';
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
 */
export default function VerifyEmail({ email, status }: { email: string; status?: string }) {
    const { auth } = usePage<SharedProps>().props;
    const { post, processing } = useForm({});
    const logout = useForm({});

    function resend(e: FormEvent) {
        e.preventDefault();
        post('/email/verification-notification', { preserveScroll: true });
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
                        Письмо со ссылкой отправлено на{' '}
                        <b className="break-all">{email ?? auth?.user?.email}</b>. Откройте его и нажмите кнопку
                        внутри — ссылка действует 24 часа.
                    </div>
                </div>

                {status && <Alert tone="success">{status}</Alert>}

                <div className="text-muted space-y-2 text-sm leading-relaxed">
                    <p>
                        Письма нет? Проверьте папку «Спам» — туда попадает почти половина писем от новых
                        отправителей.
                    </p>
                    <p>Адрес указан с опечаткой? Смените его в настройках — письмо уйдёт заново.</p>
                </div>

                <form onSubmit={resend}>
                    <Button type="submit" size="lg" block loading={processing}>
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
