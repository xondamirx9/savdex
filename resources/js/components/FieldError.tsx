import { usePage } from '@inertiajs/react';

/**
 * Ошибка поля из ответа сервера — для загрузок через router.post.
 *
 * Логотип, обложка, фото объявления и резюме уходят сразу при выборе
 * файла, мимо useForm: сервер отвечал «не тот формат» или «больше 8 МБ»,
 * а на экране не происходило ничего. name — поле («logo»); ошибки его
 * частей («images.0», «files.3») — тоже его.
 */
export function FieldError({ name }: { name: string }) {
    const errors = (usePage().props as { errors?: Record<string, string> }).errors ?? {};
    const message = Object.entries(errors).find(([key]) => key === name || key.startsWith(`${name}.`))?.[1];

    return message ? (
        <p className="hint" role="alert" style={{ color: 'var(--danger)' }}>
            {message}
        </p>
    ) : null;
}
