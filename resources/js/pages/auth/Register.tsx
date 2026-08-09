import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { useMemo, type FormEvent } from 'react';
import { Button, PasswordInput, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { routes } from '@/routes';
import { cn } from '@/lib/cn';

/**
 * Оценка надёжности пароля 0–4.
 * Правила совпадают с серверными (RegisterRequest): минимум 10 символов,
 * буквы и цифры. Клиент только подсказывает заранее — решение всё равно
 * принимает сервер, иначе проверку обойдут отключением JavaScript.
 */
function scorePassword(v: string): number {
    let s = 0;
    if (v.length >= 10) s++;
    if (v.length >= 14) s++;
    if (/[a-zа-я]/.test(v) && /[A-ZА-Я]/.test(v)) s++;
    if (/\d/.test(v)) s++;
    if (/[^\w\s]/.test(v)) s++;
    if (/^(123|qwe|password|пароль|admin)/i.test(v)) s = Math.min(s, 1);
    return Math.min(s, 4);
}

const LABELS = ['слишком простой', 'слабый', 'средний', 'хороший', 'надёжный'];
const BARS = ['bg-danger', 'bg-danger', 'bg-warning', 'bg-success', 'bg-success'];
const TEXTS = ['text-danger', 'text-danger', 'text-warning', 'text-success', 'text-success'];

export default function Register() {
    const { data, setData, post, processing, errors, clearErrors } = useForm({
        name: '',
        email: '',
        phone: '',
        password: '',
        password_confirmation: '',
        terms: false as boolean,
    });

    /**
     * Гасит ошибку поля, как только человек начал его править.
     * Красная подпись, висящая под полем, которое уже исправлено, читается
     * как «всё ещё неверно» и заставляет искать несуществующую проблему.
     */
    function update<K extends keyof typeof data>(key: K, value: (typeof data)[K]) {
        setData((d) => ({ ...d, [key]: value }));

        if (key === 'password' || key === 'password_confirmation') {
            // Несовпадение — ошибка пары, а не одного поля
            clearErrors('password', 'password_confirmation');
        } else if (errors[key as keyof typeof errors]) {
            clearErrors(key as keyof typeof errors);
        }
    }

    const strength = useMemo(() => {
        if (!data.password) return null;
        const score = scorePassword(data.password);
        const missing: string[] = [];
        if (data.password.length < 10) missing.push(`ещё ${10 - data.password.length} симв.`);
        if (!/\d/.test(data.password)) missing.push('цифру');
        if (!/[^\w\s]/.test(data.password)) missing.push('спецсимвол');
        return { score, missing };
    }, [data.password]);

    function submit(e: FormEvent) {
        e.preventDefault();
        post(routes.register, {
            onFinish: () => setData((d) => ({ ...d, password: '', password_confirmation: '' })),
        });
    }

    return (
        <AuthLayout title="Регистрация" heading="Создайте аккаунт" subheading="Бесплатно. Карта не нужна.">
            <form onSubmit={submit} className="space-y-5" noValidate>
                <TextInput
                    label="Рабочая почта"
                    type="email"
                    name="email"
                    autoComplete="email"
                    required
                    placeholder="you@company.uz"
                    value={data.email}
                    onChange={(e) => update('email', e.target.value)}
                    error={errors.email}
                    hint="На неё придёт письмо для подтверждения"
                    autoFocus
                />

                <TextInput
                    label="Ваше имя"
                    name="name"
                    autoComplete="name"
                    required
                    placeholder="Рустам Каримов"
                    value={data.name}
                    onChange={(e) => update('name', e.target.value)}
                    error={errors.name}
                />

                <TextInput
                    label="Телефон"
                    type="tel"
                    name="phone"
                    autoComplete="tel"
                    required
                    placeholder="+998 90 123-45-67"
                    value={data.phone}
                    onChange={(e) => update('phone', e.target.value)}
                    error={errors.phone}
                    hint="Понадобится для подтверждения компании"
                />

                <div>
                    <PasswordInput
                        label="Пароль"
                        name="password"
                        autoComplete="new-password"
                        required
                        placeholder="Минимум 10 символов"
                        value={data.password}
                        onChange={(e) => update('password', e.target.value)}
                        error={errors.password}
                    />
                    {strength && !errors.password && (
                        <div className="mt-2">
                            <div className="bg-canvas h-[5px] overflow-hidden rounded-full">
                                <div
                                    className={cn('h-full rounded-full transition-all', BARS[strength.score])}
                                    style={{ width: `${((strength.score + 1) / 5) * 100}%` }}
                                />
                            </div>
                            <p className="text-muted mt-1.5 text-[13px]">
                                Надёжность:{' '}
                                <b className={TEXTS[strength.score]}>{LABELS[strength.score]}</b>
                                {strength.missing.length > 0 && ` · добавьте ${strength.missing.join(', ')}`}
                            </p>
                        </div>
                    )}
                </div>

                <PasswordInput
                    label="Повторите пароль"
                    name="password_confirmation"
                    autoComplete="new-password"
                    required
                    value={data.password_confirmation}
                    onChange={(e) => update('password_confirmation', e.target.value)}
                    error={errors.password_confirmation}
                />

                <div>
                    <label
                        className={cn(
                            'flex cursor-pointer items-start gap-2.5 text-sm',
                            errors.terms && 'text-danger',
                        )}
                    >
                        <input
                            type="checkbox"
                            checked={data.terms}
                            onChange={(e) => update('terms', e.target.checked)}
                            aria-invalid={errors.terms ? true : undefined}
                            className={cn(
                                'accent-primary-700 mt-0.5 size-[18px] shrink-0 cursor-pointer',
                                errors.terms && 'outline-danger rounded-xs outline-2 outline-offset-2',
                            )}
                        />
                        <span>
                            Принимаю <a href="/terms" className="text-primary-700 hover:underline">оферту</a> и{' '}
                            <a href="/privacy" className="text-primary-700 hover:underline">
                                политику конфиденциальности
                            </a>
                        </span>
                    </label>
                    {errors.terms && <p className="text-danger mt-1.5 text-[13px]">{errors.terms}</p>}
                </div>

                <Button type="submit" size="lg" block loading={processing}>
                    Продолжить
                </Button>
            </form>

            <p className="text-muted mt-6 text-center text-sm">
                Уже есть аккаунт?{' '}
                <Link href={routes.login} className="text-primary-700 hover:underline">
                    Войти
                </Link>
            </p>
        </AuthLayout>
    );
}
