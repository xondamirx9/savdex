import { useForm } from '@inertiajs/react';
import { Mail, Smartphone } from 'lucide-react';
import { Link } from '@/components/ui/Link';
import { useEffect, useState, type FormEvent } from 'react';
import { Alert, Button, PasswordInput, TextInput } from '@/components/ui';
import { AuthLayout } from '@/layouts/AuthLayout';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

type Method = 'email' | 'phone';

/**
 * Чем входили в прошлый раз. Хранилище браузера может быть недоступно
 * — приватное окно, запрет на данные сайта: тогда открывается почта,
 * как и у пришедшего впервые.
 */
const METHOD_KEY = 'savdex.login_method';

function savedMethod(): Method | null {
    try {
        return window.localStorage.getItem(METHOD_KEY) === 'phone' ? 'phone' : null;
    } catch {
        return null;
    }
}

function rememberMethod(method: Method): void {
    try {
        window.localStorage.setItem(METHOD_KEY, method);
    } catch {
        // Нечем запомнить — переживём
    }
}

/** Номер короче — опечатка, а не телефон: код страны и сам номер. */
const PHONE_MIN_DIGITS = 8;

export default function Login({ status }: { status?: string }) {
    /*
     * Первая отрисовка — всегда почта: на сервере (SSR) хранилища
     * браузера нет, и разметка должна совпасть с той, что получит
     * гидратация. Запомненный способ подставляется сразу после неё.
     */
    const [method, setMethod] = useState<Method>('email');
    const byPhone = method === 'phone';

    useEffect(() => {
        const saved = savedMethod();

        if (saved) setMethod(saved);
    }, []);

    const { data, setData, transform, post, processing, errors, clearErrors, setError } = useForm({
        email: '',
        phone: '',
        password: '',
        remember: false as boolean,
    });

    /*
     * Сервер принимает одно поле: почту или подтверждённый номер — он
     * сам различает их по виду (AuthenticatedSessionController::store).
     * Поэтому на отправке выбранное значение уходит как «email», а на
     * экране почта и телефон живут порознь: переключил способ —
     * набранное в другом поле не мешает и на сервер не улетает.
     */
    transform((form) => ({
        email: (byPhone ? form.phone : form.email).trim(),
        password: form.password,
        remember: form.remember,
    }));

    function choose(next: Method) {
        if (next === method) return;

        setMethod(next);
        clearErrors();
        rememberMethod(next);
    }

    function submit(e: FormEvent) {
        e.preventDefault();

        /*
         * Неполный номер до сервера не доходит: там он сойдёт за неверные
         * данные и сгорит одна из пяти попыток до блокировки входа.
         */
        if (byPhone && data.phone.replace(/\D/g, '').length < PHONE_MIN_DIGITS) {
            setError('phone', t('auth.login_phone_short'));
            return;
        }

        // Пароль не должен остаться в памяти формы после отправки
        post(routes.login, { onFinish: () => setData('password', '') });
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
                {/* Чем входить — почтой или подтверждённым номером. Тот же
                    выбор, что на первом шаге регистрации (RegisterEmail),
                    только компактный: человек уже знает свой аккаунт */}
                <div role="radiogroup" aria-label={t('auth.login_method_label')} className="grid grid-cols-2 gap-3">
                    {(
                        [
                            ['email', Mail, 'auth.email_short_label'],
                            ['phone', Smartphone, 'auth.phone_label'],
                        ] as const
                    ).map(([key, Icon, label]) => {
                        const selected = method === key;

                        return (
                            <button
                                key={key}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                onClick={() => choose(key)}
                                className={cn(
                                    'group rounded-card flex cursor-pointer items-center justify-center gap-2.5 border px-3 py-3',
                                    'text-[15px] font-semibold transition duration-150 ease-out',
                                    'focus-visible:ring-primary-500 focus-visible:ring-2 focus-visible:outline-none',
                                    selected
                                        ? 'border-primary-700 bg-primary-50 text-ink'
                                        : 'bg-surface border-line text-muted hover:border-primary-500 hover:text-ink',
                                )}
                            >
                                <span
                                    className={cn(
                                        'flex size-8 items-center justify-center rounded-full transition-colors duration-150',
                                        selected
                                            ? 'bg-primary-700 text-white'
                                            : 'bg-primary-50 text-primary-700 group-hover:bg-primary-700 group-hover:text-white',
                                    )}
                                >
                                    <Icon aria-hidden className="size-[18px]" />
                                </span>
                                {t(label)}
                            </button>
                        );
                    })}
                </div>

                {byPhone ? (
                    /* key: переключение способа пересоздаёт поле, и autoFocus
                       переводит в него курсор — иначе React оставил бы прежний
                       input и в него пришлось бы целиться мышью */
                    <TextInput
                        key="phone"
                        label={t('auth.phone_label')}
                        type="tel"
                        inputMode="tel"
                        name="phone"
                        /* Для менеджера паролей телефон — то же имя учётной
                           записи, что и почта: иначе он не свяжет его с паролем */
                        autoComplete="username"
                        required
                        placeholder={t('auth.phone_placeholder')}
                        value={data.phone}
                        onChange={(e) => {
                            setData('phone', e.target.value);
                            if (errors.phone || errors.email) clearErrors('phone', 'email');
                        }}
                        /**
                         * Сервер отдаёт единое сообщение для «нет пользователя»
                         * и «неверный пароль» и вешает его на поле почты —
                         * см. AuthenticatedSessionController (NEG-02, NEG-06d).
                         */
                        error={errors.phone ?? errors.email}
                        hint={t('auth.login_phone_hint')}
                        autoFocus
                    />
                ) : (
                    <TextInput
                        key="email"
                        label={t('auth.login_email_label')}
                        type="email"
                        inputMode="email"
                        autoCapitalize="none"
                        autoCorrect="off"
                        spellCheck={false}
                        name="email"
                        autoComplete="username"
                        required
                        placeholder={t('auth.email_placeholder')}
                        value={data.email}
                        onChange={(e) => {
                            setData('email', e.target.value);
                            if (errors.email) clearErrors('email');
                        }}
                        error={errors.email}
                        autoFocus
                    />
                )}

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
