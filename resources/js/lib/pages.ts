import type { ComponentType } from 'react';

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

    return (await loader()).default;
}
