import { router } from '@inertiajs/react';
import { routes } from '@/routes';

/**
 * Отметить уведомление прочитанным, не уходя со страницы: так открываются
 * внешние ссылки рассылок. Сервер в ответ ведёт назад — Inertia просто
 * обновит счётчик, а ссылка уже открыта в новой вкладке.
 */
export function markRead(id: number, read: boolean): void {
    if (read) return;

    router.post(routes.notificationRead(id), {}, { preserveScroll: true, preserveState: true });
}
