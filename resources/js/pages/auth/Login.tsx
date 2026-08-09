import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import type { FormEvent } from 'react';
import { Alert, Button, PasswordInput, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { routes } from '@/routes';

export default function Login({ status }: { status?: string }) {
    const { data, setData, post, processing, errors } = useForm({
        email: '',
        password: '',
        remember: false as boolean,
    });

    function submit(e: FormEvent) {
        e.preventDefault();
        // Пароль не должен остаться в памяти формы после отправки
        post(routes.login, { onFinish: () => setData('password', '') });
    }

    return (
        <AuthLayout
            title="Вход"
            heading="С возвращением"
            subheading="Войдите, чтобы вернуться к объявлениям и контактам."
        >
            {status && (
                <Alert tone="success" className="mb-5">
                    {status}
                </Alert>
            )}

            <form onSubmit={submit} className="space-y-5" noValidate>
                <TextInput
                    label="Почта"
                    type="email"
                    name="email"
                    autoComplete="email"
                    required
                    value={data.email}
                    onChange={(e) => setData('email', e.target.value)}
                    /**
                     * Сервер отдаёт единое сообщение для «нет пользователя»
                     * и «неверный пароль» и вешает его на поле почты —
                     * см. AuthenticatedSessionController (NEG-02, NEG-06d).
                     */
                    error={errors.email}
                    autoFocus
                />

                {/* Ссылка «Забыли?» стоит под полем, а не в одной строке с подписью.
                    Раньше подпись подменялась на пустую (label=""), чтобы освободить
                    место под ссылку, и <label> оставался с одной звёздочкой —
                    скринридер читал поле как «звёздочка». */}
                <div>
                    <PasswordInput
                        label="Пароль"
                        name="password"
                        autoComplete="current-password"
                        required
                        value={data.password}
                        onChange={(e) => setData('password', e.target.value)}
                        error={errors.password}
                    />
                    <div className="mt-1.5 text-right">
                        <Link href={routes.passwordRequest} className="text-primary-700 text-sm hover:underline">
                            Забыли пароль?
                        </Link>
                    </div>
                </div>

                <label className="flex cursor-pointer items-start gap-2.5 text-sm">
                    <input
                        type="checkbox"
                        checked={data.remember}
                        onChange={(e) => setData('remember', e.target.checked)}
                        className="accent-primary-700 mt-0.5 size-[18px] shrink-0 cursor-pointer"
                    />
                    Запомнить меня на этом устройстве
                </label>

                <Button type="submit" size="lg" block loading={processing}>
                    Войти
                </Button>
            </form>

            <p className="text-muted mt-6 text-center text-sm">
                Нет аккаунта?{' '}
                <Link href={routes.register} className="text-primary-700 hover:underline">
                    Зарегистрируйтесь
                </Link>
            </p>
        </AuthLayout>
    );
}
