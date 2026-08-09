import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft } from 'lucide-react';
import type { FormEvent } from 'react';
import { Alert, Button, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { routes } from '@/routes';

export default function ForgotPassword({ status }: { status?: string }) {
    const { data, setData, post, processing, errors } = useForm({ email: '' });

    function submit(e: FormEvent) {
        e.preventDefault();
        post('/forgot-password', { preserveScroll: true });
    }

    return (
        <AuthLayout
            title="Восстановление пароля"
            heading="Забыли пароль?"
            subheading="Укажите почту, на которую зарегистрирован аккаунт — пришлём ссылку для смены пароля."
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
                        Ссылка действует 60 минут. Если письмо не пришло за пару минут, проверьте папку «Спам»
                        или запросите новое.
                    </p>
                    <Button type="button" size="lg" block variant="secondary" onClick={() => post('/forgot-password')}>
                        Отправить ещё раз
                    </Button>
                </div>
            ) : (
                <form onSubmit={submit} className="space-y-5" noValidate>
                    <TextInput
                        label="Рабочая почта"
                        type="email"
                        name="email"
                        autoComplete="email"
                        required
                        placeholder="you@company.uz"
                        value={data.email}
                        onChange={(e) => setData('email', e.target.value)}
                        error={errors.email}
                        autoFocus
                    />
                    <Button type="submit" size="lg" block loading={processing}>
                        Прислать ссылку
                    </Button>
                </form>
            )}

            <p className="text-muted mt-6 text-center text-sm">
                <Link href={routes.login} className="text-primary-700 inline-flex items-center gap-1.5 hover:underline">
                    <ArrowLeft aria-hidden className="size-4" />
                    Вернуться ко входу
                </Link>
            </p>
        </AuthLayout>
    );
}
