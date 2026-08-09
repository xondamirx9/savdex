import { Link as InertiaLink } from '@inertiajs/react';
import type { ComponentProps } from 'react';

import { localize } from '@/lib/locale';

type Props = ComponentProps<typeof InertiaLink>;

/**
 * Ссылка, знающая про язык.
 *
 * Подставляет в адрес языковой префикс текущей страницы. Обёртка
 * нужна именно вокруг ссылки, а не только вокруг перехода: адрес
 * должен быть правильным в самой разметке — поисковик читает href,
 * а человек копирует его правой кнопкой.
 *
 * Импортируется вместо Link из @inertiajs/react во всех местах,
 * кроме тех, где адрес заведомо внешний.
 */
export function Link({ href, ...props }: Props) {
    return <InertiaLink href={typeof href === 'string' ? localize(href) : href} {...props} />;
}
