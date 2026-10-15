import '@fontsource/cormorant-garamond/latin-400.css';
import '@fontsource/cormorant-garamond/latin-ext-400.css';
import '@fontsource/cormorant-garamond/cyrillic-400.css';
import '@fontsource/cormorant-garamond/cyrillic-ext-400.css';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-ext-400.css';
import '@fontsource/inter/cyrillic-400.css';
import '@fontsource/inter/cyrillic-ext-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-ext-500.css';
import '@fontsource/inter/cyrillic-500.css';
import '@fontsource/inter/cyrillic-ext-500.css';
import '../../../css/ilmora.css';
import { Head, usePage } from '@inertiajs/react';
import type { ReactNode } from 'react';
import { IlmoraLogo } from '@/components/ilmora/IlmoraLogo';
import { t } from '@/lib/i18n';
import { stripLocale } from '@/lib/locale';
import type { SharedProps } from '@/types';

/** Языки ILMORA: русский и узбекский */
const LANGS = [
    { code: 'ru', label: 'RU' },
    { code: 'uz', label: 'UZ' },
] as const;

/**
 * Раскладка страниц ILMORA: слева тёмно-зелёная панель со знаком, справа
 * форма на светлом фоне; на телефоне — одна колонка. Цвета и шрифты —
 * ILMORA (css/ilmora.css), не Savdex: всё внутри .ilmora.
 */
export function IlmoraLayout({ title, children }: { title: string; children: ReactNode }) {
    const page = usePage<SharedProps>();
    const { locale } = page.props;
    // Смена языка — ?hl=: сервер запомнит выбор и уведёт на адрес этого языка
    const path = stripLocale(new URL(page.url, 'http://savdex.uz').pathname);

    return (
        <div className="ilmora">
            <Head title={title} />

            <div className="ilmora-shell">
                <aside className="ilmora-aside">
                    <div className="ilmora-aside__top">
                        <IlmoraLogo />
                        <nav className="ilmora-langs" aria-label={t('ilmora.languages')}>
                            {LANGS.map((lang) => (
                                <a
                                    key={lang.code}
                                    href={`${path}?hl=${lang.code}`}
                                    hrefLang={lang.code}
                                    aria-current={locale === lang.code}
                                >
                                    {lang.label}
                                </a>
                            ))}
                        </nav>
                    </div>

                    <div className="ilmora-aside__pitch">
                        {/* Не заголовок: h1 страницы — в карточке справа */}
                        <p className="ilmora-aside__title">{t('ilmora.aside_title')}</p>
                        <span className="ilmora-aside__rule" aria-hidden />
                        <p className="ilmora-aside__lead">{t('ilmora.aside_lead')}</p>
                    </div>

                    <p className="ilmora-aside__foot">{t('ilmora.via_savdex')} · savdex.uz</p>
                </aside>

                <main className="ilmora-main">{children}</main>
            </div>
        </div>
    );
}
