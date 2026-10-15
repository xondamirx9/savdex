import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { useState, type FormEvent } from 'react';
import { CaptchaGrid } from '@/components/auth/CaptchaGrid';
import { Alert, Button, PasswordInput, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

export default function Login({ status, captcha = false }: { status?: string; captcha?: boolean }) {
    const { data, setData, post, processing, errors } = useForm({
        email: '',
        password: '',
        remember: false as boolean,
        captcha: [] as number[],
    });
    // Задание капчи одноразовое: после каждой отправки — новое
    const [captchaKey, setCaptchaKey] = useState(0);

    function submit(e: FormEvent) {
        e.preventDefault();
        // Пароль не должен остаться в памяти формы после отправки
        post(routes.login, {
            onFinish: () => {
                setData('password', '');
                setCaptchaKey((k) => k + 1);
            },
        });
    }

    return (
        <AuthLayout
            title={t('auth.login_title')}
            heading={t('auth.login_heading')}
            subheading={t('auth.login_subheading')}
        >
            {status && (
                <Alert tone="success" className="mb-5">
                    {status}
                </Alert>
            )}

            <form onSubmit={submit} className="space-y-5" noValidate>
                {/* Почта или подтверждённый телефон (регистрация по телефону):
                    type="text", иначе браузер не пустит номер в поле почты */}
                <TextInput
                    label={t('auth.login_identifier')}
                    type="text"
                    inputMode="email"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    name="email"
                    autoComplete="username"
                    required
                    value={data.email}
                    onChange={(e) => setData('email', e.target.value)}
                    /**
                     * Сервер отдаёт единое сообщение для «нет пользователя»
                     * и «неверный пароль» и вешает его на поле почты —
                     * см. AuthenticatedSessionController (NEG-02, NEG-06d).
                     */
                    error={errors.email}
                    hint={t('auth.login_identifier_hint')}
                    autoFocus
                />

                {/* Ссылка «Забыли?» стоит под полем, а не в одной строке с подписью.
                    Раньше подпись подменялась на пустую (label=""), чтобы освободить
                    место под ссылку, и <label> оставался с одной звёздочкой —
                    скринридер читал поле как «звёздочка». */}
                <div>
                    <PasswordInput
                        label={t('auth.password_label')}
                        name="password"
                        autoComplete="current-password"
                        required
                        value={data.password}
                        onChange={(e) => setData('password', e.target.value)}
                        error={errors.password}
                    />
                    <div className="mt-1.5 text-right">
                        <Link href={routes.passwordRequest} className="text-primary-700 text-sm hover:underline">
                            {t('auth.forgot_password')}
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
                    {t('auth.remember_me')}
                </label>

                {captcha && (
                    <CaptchaGrid
                        purpose="login"
                        value={data.captcha}
                        onChange={(cells) => setData('captcha', cells)}
                        error={errors.captcha}
                        reloadKey={captchaKey}
                    />
                )}

                <Button type="submit" size="lg" block loading={processing}>
                    {t('auth.login_button')}
                </Button>
            </form>

            <p className="text-muted mt-6 text-center text-sm">
                {t('auth.no_account')}{' '}
                <Link href={routes.register} className="text-primary-700 hover:underline">
                    {t('auth.register_link')}
                </Link>
            </p>
        </AuthLayout>
    );
}
