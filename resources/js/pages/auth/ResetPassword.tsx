import { useForm } from '@inertiajs/react';
import type { FormEvent } from 'react';
import { Button, PasswordInput, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';

export default function ResetPassword({ token, email }: { token: string; email: string }) {
    const { data, setData, post, processing, errors } = useForm({
        token,
        email,
        password: '',
        password_confirmation: '',
    });

    function submit(e: FormEvent) {
        e.preventDefault();
        post('/reset-password', {
            onFinish: () => setData((d) => ({ ...d, password: '', password_confirmation: '' })),
        });
    }

    return (
        <AuthLayout title="Новый пароль" heading="Придумайте новый пароль" subheading="Ссылка действует 60 минут с момента запроса.">
            <form onSubmit={submit} className="space-y-5" noValidate>
                <TextInput
                    label="Почта"
                    type="email"
                    name="email"
                    autoComplete="email"
                    required
                    value={data.email}
                    onChange={(e) => setData('email', e.target.value)}
                    error={errors.email}
                />
                <PasswordInput
                    label="Новый пароль"
                    name="password"
                    autoComplete="new-password"
                    required
                    placeholder="Минимум 10 символов"
                    value={data.password}
                    onChange={(e) => setData('password', e.target.value)}
                    error={errors.password}
                    autoFocus
                />
                <PasswordInput
                    label="Повторите пароль"
                    name="password_confirmation"
                    autoComplete="new-password"
                    required
                    value={data.password_confirmation}
                    onChange={(e) => setData('password_confirmation', e.target.value)}
                    error={errors.password_confirmation}
                />
                <Button type="submit" size="lg" block loading={processing}>
                    Сохранить пароль
                </Button>
            </form>
        </AuthLayout>
    );
}
