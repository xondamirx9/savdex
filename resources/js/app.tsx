import '../css/app.css';

import { createInertiaApp, router } from '@inertiajs/react';
import { polyfillCountryFlagEmojis } from 'country-flag-emoji-polyfill';
import twemojiFlagsFont from 'country-flag-emoji-polyfill/dist/TwemojiCountryFlags.woff2?url';
import { createRoot, hydrateRoot } from 'react-dom/client';
import { resolvePage } from '@/lib/pages';
import { localize, setLocale } from '@/lib/locale';
import { setTranslations } from '@/lib/i18n';

const appName = import.meta.env.VITE_APP_NAME ?? 'SAVDEX';

/*
 * Флаги-эмодзи на Windows: система не рисует региональные пары
 * (🇺🇿 показывался как «uz» на каждой карточке — а Windows это
 * почти весь десктоп в Узбекистане). Полифилл подключает шрифт
 * Twemoji Country Flags только там, где флаги не рендерятся;
 * .flag в CSS ставит его первым в стеке. Шрифт — со своего домена
 * через сборку, а не с чужого CDN (docs/DESIGN.md §3).
 */
polyfillCountryFlagEmojis('Twemoji Country Flags', twemojiFlagsFont);

/**
 * Язык текущей страницы — из данных, которые пришли с сервером.
 *
 * Обновляется на каждом переходе: язык меняется вместе со страницей,
 * и адрес следующего перехода должен собираться уже по новому.
 */
router.on('navigate', (event) => {
    const locale = (event.detail.page.props as { locale?: string }).locale;

    if (typeof locale === 'string') setLocale(locale);
});

/**
 * Переходы, вызванные из кода.
 *
 * Ссылки язык подставляют сами (см. components/ui/Link), а
 * router.post и router.get идут мимо них — например отправка формы
 * фильтров или удаление объявления. Без этого человек, работающий
 * на узбекском, после первого же такого действия оказывался бы
 * на русской версии.
 */
router.on('before', (event) => {
    const { visit } = event.detail;

    if (typeof visit.url === 'object' && visit.url instanceof URL) {
        visit.url.pathname = localize(visit.url.pathname);
    }
});

void createInertiaApp({
    title: (title) => (title ? `${title} · ${appName}` : appName),
    resolve: resolvePage,
    setup({ el, App, props }) {
        if (!el) {
            throw new Error('Не найден корневой элемент Inertia. Проверьте @inertia в resources/views/app.blade.php');
        }

        // До первой отрисовки: иначе ссылки первой страницы соберутся
        // без языка, а надписи — из ключей вместо перевода
        const shared = props.initialPage.props as {
            locale?: string;
            translations?: Record<string, unknown> | null;
        };

        if (typeof shared.locale === 'string') setLocale(shared.locale);
        if (shared.translations) setTranslations(shared.translations, shared.locale ?? 'ru');

        // SSR отдаёт готовую разметку — её нужно гидрировать, а не рендерить
        // заново, иначе преимущество для SEO теряется, а разметка мигает.
        if (el.hasChildNodes()) {
            hydrateRoot(el, <App {...props} />);
            return;
        }

        createRoot(el).render(<App {...props} />);
    },
    progress: { color: '#1d4ed8' },
});
