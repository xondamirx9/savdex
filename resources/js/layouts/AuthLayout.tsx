import { Head, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Check, Star } from 'lucide-react';
import type { ReactNode } from 'react';
import { LangSwitcher } from '@/components/LangSwitcher';
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
    const { flash, authReview, locale, localeLinks } = usePage<SharedProps>().props;

    // Язык выбирают и до входа: человек со ссылкой на русскую страницу
    // должен суметь перейти на свой, не возвращаясь на главную
    const lang = <LangSwitcher locale={locale ?? 'ru'} links={localeLinks ?? []} />;

    return (
        <>
            <Head title={title} />
            <MaintenanceOverlay />
            <a href="#form" className="skip-link">
                {t('auth.skip_to_form')}
            </a>

            {/* Тёмный экран входа (вариант C): слева заголовок, выгоды и
                отзыв о площадке, справа карточка формы. Цвета форм
                переопределены переменными в .auth-dark — поля, списки
                и кнопки на всех экранах входа темнеют сами */}
            <div className="auth-dark">
                <div className={cn('auth-shell', wide && 'auth-shell--wide')}>
                    {/* На компьютере — в правом верхнем углу, на одной линии
                        с логотипом левой панели */}
                    <div className="auth-lang">{lang}</div>

                    <aside className="auth-aside">
                        <Link href="/" className="auth-logo" aria-label={t('auth.home_aria')}>
                            <Logo inverted />
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
                        {/* На телефоне левой панели нет: логотип и язык — строкой над формой */}
                        <div className="auth-mobile-bar">
                            <Link href="/" className="auth-logo" aria-label={t('auth.home_aria')}>
                                <Logo inverted />
                            </Link>
                            {lang}
                        </div>

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
