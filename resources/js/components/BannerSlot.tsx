import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { t } from '@/lib/i18n';

export type BannerData = {
    key: string;
    url: string | null;
    alt: string;
    image: string;
    imageMobile: string | null;
    focal: string;
    dismissible: boolean;
    dismissDays: number;
};

/**
 * Помнит закрытые баннеры.
 *
 * Хранилище браузера может быть недоступно — приватное окно, запрет
 * на данные сайта. Тогда баннер просто показывается: акция важнее
 * памяти о том, что её однажды закрыли.
 */
function dismissedUntil(key: string): number | null {
    try {
        const raw = window.localStorage.getItem(key);
        return raw ? Number(raw) : null;
    } catch {
        return null;
    }
}

function remember(key: string, days: number): void {
    try {
        window.localStorage.setItem(key, String(Date.now() + days * 86_400_000));
    } catch {
        // Нечем запомнить — переживём
    }
}

/**
 * Баннер акции.
 *
 * Картинок две: широкая для компьютера и узкая для телефона. Если
 * узкой нет, широкая обрезается по точке фокуса — широкий макет
 * на узком экране красиво не обрежется сам.
 */
export function BannerSlot({ banner }: { banner: BannerData | null }) {
    /*
     * Сперва баннер скрыт всегда.
     *
     * Разметка приходит с сервера, а про закрытие знает только браузер:
     * покажи мы баннер сразу, закрытый успел бы мигнуть перед тем,
     * как исчезнуть.
     */
    const [shown, setShown] = useState(false);

    useEffect(() => {
        if (!banner) return;

        const until = dismissedUntil(banner.key);
        setShown(until === null || until < Date.now());
    }, [banner]);

    if (!banner || !shown) return null;

    const close = () => {
        remember(banner.key, banner.dismissDays);
        setShown(false);
    };

    const picture = (
        <picture>
            {banner.imageMobile && <source media="(max-width: 640px)" srcSet={banner.imageMobile} />}
            <img
                src={banner.image}
                alt={banner.alt}
                className="banner-slot__image"
                style={{ objectPosition: banner.focal }}
                loading="lazy"
                decoding="async"
            />
        </picture>
    );

    return (
        <section className="banner-slot" aria-label={banner.alt}>
            {banner.url ? (
                <a href={banner.url} className="banner-slot__link">
                    {picture}
                </a>
            ) : (
                picture
            )}

            {banner.dismissible && (
                <button type="button" className="banner-slot__close" onClick={close} aria-label={t('common.close')}>
                    <X aria-hidden className="size-4" />
                </button>
            )}
        </section>
    );
}
