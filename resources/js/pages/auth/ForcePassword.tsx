import { useForm } from '@inertiajs/react';
import type { FormEvent } from 'react';
import { Alert, Button, PasswordInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';

/**
 * Смена пароля, выданного администратором.
 *
 * Ссылки «пропустить» здесь нет намеренно: пока пароль знают двое,
 * доступ нельзя считать принадлежащим пользователю.
 */
export default function ForcePassword() {
    const { data, setData, post, processing, errors, clearErrors } = useForm({
        password: '',
        password_confirmation: '',
    });

    function update(key: 'password' | 'password_confirmation', value: string) {
        setData((d) => ({ ...d, [key]: value }));
        clearErrors('password', 'password_confirmation');
    }

    function submit(e: FormEvent) {
        e.preventDefault();
        post('/password/change', {
            onFinish: () => setData({ password: '', password_confirmation: '' }),
        });
    }

    return (
        <AuthLayout
            title="Смена пароля"
            heading="Смените пароль"
            subheading="Первый пароль выдал администратор — его нужно заменить своим."
        >
            <Alert tone="warning" className="mb-5">
                Пока пароль не изменён, остальные разделы недоступны: выданный вручную пароль знаете не только вы.
            </Alert>

            <form onSubmit={submit} className="space-y-5" noValidate>
                <PasswordInput
                    label="Новый пароль"
                    name="password"
                    autoComplete="new-password"
                    required
                    placeholder="Минимум 10 символов"
                    value={data.password}
                    onChange={(e) => update('password', e.target.value)}
                    error={errors.password}
                    autoFocus
                />
                <PasswordInput
                    label="Повторите пароль"
                    name="password_confirmation"
                    autoComplete="new-password"
                    required
                    value={data.password_confirmation}
                    onChange={(e) => update('password_confirmation', e.target.value)}
                    error={errors.password_confirmation}
                />
                <Button type="submit" size="lg" block loading={processing}>
                    Сохранить и продолжить
                </Button>
            </form>
        </AuthLayout>
    );
}
