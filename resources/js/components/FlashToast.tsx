import { usePage } from '@inertiajs/react';
import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Alert, type AlertTone } from '@/components/ui/Alert';
import { t } from '@/lib/i18n';
import type { SharedProps } from '@/types';

/**
 * Итог действия (flash) — плашкой у нижнего края экрана.
 *
 * Сообщение в начале страницы терялось: формы внизу длинных страниц
 * (касса, массовые действия) отправляются с preserveScroll, и ответ
 * «счёт выставлен» оказывался в тысячах пикселей выше. А на витрине
 * сообщений не было вовсе — «нет кредитов» на открытии контакта не
 * видел никто. Плашка видна там, где человек сейчас, и уходит сама.
 */
export function FlashToast() {
    const { flash } = usePage<SharedProps>().props;
    const [shown, setShown] = useState<{ tone: AlertTone; text: string } | null>(null);

    useEffect(() => {
        const next = flash?.error
            ? { tone: 'danger' as const, text: flash.error }
            : flash?.warning
              ? { tone: 'warning' as const, text: flash.warning }
              : flash?.success
                ? { tone: 'success' as const, text: flash.success }
                : null;

        setShown(next);
        if (!next) return;

        // Ошибку читают дольше: она остаётся, пока её не закроют
        if (next.tone === 'danger') return;
        const timer = window.setTimeout(() => setShown(null), 6000);
        return () => window.clearTimeout(timer);
    }, [flash]);

    if (!shown) return null;

    return (
        <div className="flash-toast">
            <Alert tone={shown.tone} className="flash-toast-box">
                <span className="flash-toast-text">{shown.text}</span>
                <button
                    type="button"
                    className="flash-toast-close"
                    aria-label={t('common.close')}
                    onClick={() => setShown(null)}
                >
                    <X aria-hidden className="size-4" />
                </button>
            </Alert>
        </div>
    );
}
