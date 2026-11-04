import { createElement, type ComponentType } from 'react';
import { setTranslations } from '@/lib/i18n';

type PageModule = { default: ComponentType<Record<string, unknown>> };

/**
 * Реестр страниц Inertia.
 *
 * Типизируем import.meta.glob явно: без этого он отдаёт `unknown`,
 * и резолвер Inertia не проходит проверку типов. Штатный
 * resolvePageComponent из laravel-vite-plugin здесь не используется —
 * он теряет типы на том же месте.
 */
const pages = import.meta.glob<PageModule>('../pages/**/*.tsx');

export async function resolvePage(name: string): Promise<ComponentType<Record<string, unknown>>> {
    const path = `../pages/${name}.tsx`;
    const loader = pages[path];

    if (!loader) {
        // Явная ошибка вместо пустого экрана: опечатку в Inertia::render()
        // иначе искать долго — страница просто не отрисуется.
        throw new Error(
            `Страница Inertia не найдена: ${name}. Ожидался файл resources/js/pages/${name}.tsx`,
        );
    }

    const cached = wrapped.get(path);

    if (cached) return cached;

    const Page = (await loader()).default;
    // Новый словарь (сменили язык без перезагрузки) — до отрисовки
    // страницы: иначе надписи остались бы на прежнем языке
    const WithTranslations = (props: Record<string, unknown>) => {
        const translations = props.translations as Record<string, unknown> | null | undefined;

        if (translations) setTranslations(translations, String(props.locale ?? 'ru'));

        return createElement(Page, props);
    };

    wrapped.set(path, WithTranslations);

    return WithTranslations;
}

/** Обёртка страницы — одна на страницу: иначе каждый переход пересоздавал бы её */
const wrapped = new Map<string, ComponentType<Record<string, unknown>>>();
