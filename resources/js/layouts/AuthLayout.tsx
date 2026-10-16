import { Head, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Check, Moon, Star, Sun } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Alert, Logo } from '@/components/ui';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import type { SharedProps } from '@/types';
import { MaintenanceOverlay } from '@/components/MaintenanceOverlay';

/**
 * Аргументы левой панели. Функция, а не константа модуля: подписи
 * берутся из словаря, а он приходит с сервером после загрузки файла.
 */
const benefits = (): string[] => [
    t('auth.benefit_free'),
    t('auth.benefit_limits'),
    t('auth.benefit_no_fee'),
    t('auth.benefit_contact'),
];

type AuthTheme = 'dark' | 'light';

/** Выбор темы помнит браузер; по умолчанию экран тёмный */
const THEME_KEY = 'savdex-auth-theme';

function storedTheme(): AuthTheme {
    try {
        return typeof window !== 'undefined' && window.localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark';
    } catch {
        // Приватный режим или запрет хранилища — просто тёмная
        return 'dark';
    }
}

/**
 * Раскладка экранов входа и регистрации.
 * Левая панель с аргументами скрывается ниже 1024 px: на телефоне
 * она отодвигает форму за экран и мешает, а не помогает.
 */
export function AuthLayout({
    wide = false,
    title,
    heading,
    subheading,
    aside,
    children,
}: {
    /**
     * Широкая колонка формы. Нужна там, где в строку встают варианты
     * выбора: в 380 px три карточки роли сжимаются до нечитаемых
     * столбиков по букве в строке.
     */
    wide?: boolean;
    title: string;
    heading: string;
    subheading?: string;
    /**
     * Своё под аргументами левой панели — только у той страницы, что его
     * передала (кнопка ILMORA на первом шаге регистрации, но не на входе).
     * На телефоне панели нет — то же стоит под формой.
     */
    aside?: ReactNode;
    children: ReactNode;
}) {
    /*
     * Ошибка формы без поля: «слишком много попыток» (429 у отправки
     * формы возвращается сюда же с flash error, см. bootstrap/app.php)
     * и лимит регистраций. Без неё кнопка молча ничего не делала —
     * со стороны это «регистрация не проходит».
     */
    const { flash, authReview } = usePage<SharedProps>().props;
    const [theme, setTheme] = useState<AuthTheme>(storedTheme);
    const dark = theme === 'dark';

    function toggleTheme() {
        const next: AuthTheme = dark ? 'light' : 'dark';
        setTheme(next);
        try {
            window.localStorage.setItem(THEME_KEY, next);
        } catch {
            // Не сохранилось — тема всё равно сменится до перезагрузки
        }
    }

    return (
        <>
            <Head title={title} />
            <MaintenanceOverlay />
            <a href="#form" className="skip-link">
                {t('auth.skip_to_form')}
            </a>

            {/* Экран входа (вариант C): слева заголовок, выгоды и отзыв о
                площадке, справа карточка формы. Тёмный по умолчанию, светлый —
                по кнопке в углу. В тёмной цвета форм переопределены
                переменными в .auth-dark — поля, списки и кнопки темнеют сами */}
            <div className={cn('auth-screen', dark && 'auth-dark')}>
                <button
                    type="button"
                    className="auth-theme"
                    onClick={toggleTheme}
                    aria-label={dark ? t('auth.theme_light') : t('auth.theme_dark')}
                    title={dark ? t('auth.theme_light') : t('auth.theme_dark')}
                >
                    {dark ? <Sun aria-hidden className="size-5" /> : <Moon aria-hidden className="size-5" />}
                </button>

                <div className={cn('auth-shell', wide && 'auth-shell--wide')}>
                    <aside className="auth-aside">
                        <Link href="/" className="auth-logo" aria-label={t('auth.home_aria')}>
                            <Logo inverted={dark} />
                        </Link>

                        <div className="auth-pitch">
                            {/* Не заголовок: структурный h1 страницы — в форме справа */}
                            <p className="auth-hero">
                                {t('auth.hero_line1')} <span>{t('auth.hero_line2')}</span>
                            </p>
                            <ul className="auth-benefits">
                                {benefits().map((text) => (
                                    <li key={text}>
                                        <Check aria-hidden className="size-4" />
                                        {text}
                                    </li>
                                ))}
                            </ul>

                            {aside && <div className="auth-aside-extra">{aside}</div>}

                            {/* Настоящий опубликованный отзыв о площадке; нет такого —
                                блока нет, выдумывать отзыв нельзя */}
                            {authReview && (
                                <figure className="auth-review">
                                    <span className="auth-stars" aria-label={`${authReview.rating} / 5`}>
                                        {Array.from({ length: 5 }, (_, i) => (
                                            <Star
                                                key={i}
                                                aria-hidden
                                                className={cn('size-4', i < authReview.rating && 'is-on')}
                                            />
                                        ))}
                                    </span>
                                    <blockquote>«{authReview.body}»</blockquote>
                                    <figcaption>
                                        <span className="auth-avatar" aria-hidden>
                                            {authReview.initials}
                                        </span>
                                        {authReview.author}
                                    </figcaption>
                                </figure>
                            )}
                        </div>

                        <p className="auth-copy">{t('auth.copyright')}</p>
                    </aside>

                    <main id="form" className="auth-main">
                        <Link href="/" className="auth-logo auth-logo--mobile" aria-label={t('auth.home_aria')}>
                            <Logo inverted={dark} />
                        </Link>

                        <div className="auth-card">
                            <h1 className="auth-title">{heading}</h1>
                            {subheading && <p className="auth-sub">{subheading}</p>}

                            {flash?.error && (
                                <Alert tone="danger" className="mt-6">
                                    {flash.error}
                                </Alert>
                            )}

                            <div className="mt-6">{children}</div>
                        </div>

                        {aside && <div className="auth-aside-extra auth-aside-extra--mobile">{aside}</div>}
                    </main>
                </div>
            </div>
        </>
    );
}
