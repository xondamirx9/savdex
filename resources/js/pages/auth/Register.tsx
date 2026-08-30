import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { useMemo, type FormEvent } from 'react';
import { Button, PasswordInput, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { t } from '@/lib/i18n';
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
        if (data.password.length < 10) missing.push(t('auth.missing_length', { count: 10 - data.password.length }));
        if (!/\d/.test(data.password)) missing.push(t('auth.missing_digit'));
        if (!/[^\w\s]/.test(data.password)) missing.push(t('auth.missing_special'));
        return { score, missing };
    }, [data.password]);

    function submit(e: FormEvent) {
        e.preventDefault();
        post(routes.register, {
            onFinish: () => setData((d) => ({ ...d, password: '', password_confirmation: '' })),
        });
    }

    return (
        <AuthLayout
            title={t('auth.register_title')}
            heading={t('auth.register_heading')}
            subheading={t('auth.register_subheading')}
        >
            <form onSubmit={submit} className="space-y-5" noValidate>
                <TextInput
                    label={t('auth.email_label')}
                    type="email"
                    name="email"
                    autoComplete="email"
                    required
                    placeholder={t('auth.email_placeholder')}
                    value={data.email}
                    onChange={(e) => update('email', e.target.value)}
                    error={errors.email}
                    hint={t('auth.email_hint')}
                    autoFocus
                />

                <TextInput
                    label={t('auth.name_label')}
                    name="name"
                    autoComplete="name"
                    required
                    placeholder={t('auth.name_placeholder')}
                    value={data.name}
                    onChange={(e) => update('name', e.target.value)}
                    error={errors.name}
                />

                <TextInput
                    label={t('auth.phone_label')}
                    type="tel"
                    name="phone"
                    autoComplete="tel"
                    required
                    placeholder={t('auth.phone_placeholder')}
                    value={data.phone}
                    onChange={(e) => update('phone', e.target.value)}
                    error={errors.phone}
                    hint={t('auth.phone_hint')}
                />

                <div>
                    <PasswordInput
                        label={t('auth.password_label')}
                        name="password"
                        autoComplete="new-password"
                        required
                        placeholder={t('auth.password_placeholder')}
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
                                {t('auth.strength_label')}{' '}
                                <b className={TEXTS[strength.score]}>{t(`auth.strength_${strength.score}`)}</b>
                                {strength.missing.length > 0 &&
                                    ` · ${t('auth.strength_add', { list: strength.missing.join(', ') })}`}
                            </p>
                        </div>
                    )}
                </div>

                <PasswordInput
                    label={t('auth.password_confirm_label')}
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
                        {/* Порядок слов зависит от языка (в узбекском и турецком
                            глагол стоит в конце), поэтому фраза собирается из
                            префикса, двух ссылок, союза и суффикса */}
                        <span>
                            {t('auth.terms_prefix')} <a href="/terms" className="text-primary-700 hover:underline">{t('auth.terms_offer')}</a>{' '}
                            {t('auth.terms_and')}{' '}
                            <a href="/privacy" className="text-primary-700 hover:underline">
                                {t('auth.terms_privacy')}
                            </a>
                            {t('auth.terms_suffix')}
                        </span>
                    </label>
                    {errors.terms && <p className="text-danger mt-1.5 text-[13px]">{errors.terms}</p>}
                </div>

                <Button type="submit" size="lg" block loading={processing}>
                    {t('auth.continue')}
                </Button>
            </form>

            <p className="text-muted mt-6 text-center text-sm">
                {t('auth.have_account')}{' '}
                <Link href={routes.login} className="text-primary-700 hover:underline">
                    {t('auth.login_link')}
                </Link>
            </p>
        </AuthLayout>
    );
}
