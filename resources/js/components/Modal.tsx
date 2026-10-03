import { X } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';
import { t } from '@/lib/i18n';

/**
 * Модальное окно.
 *
 * Появилось после того, как подтверждение продвижения выводилось
 * блоком внизу страницы: человек нажимал «Применить» и не видел
 * никакой реакции — форма была за пределами экрана, и действие
 * читалось как неработающее.
 *
 * Ловушка фокуса, Esc и блокировка прокрутки фона — A11Y-02 из QA.md.
 */
export function Modal({
    open,
    onClose,
    title,
    description,
    footer,
    children,
    width = 480,
}: {
    open: boolean;
    onClose: () => void;
    title: string;
    description?: ReactNode;
    footer?: ReactNode;
    children?: ReactNode;
    width?: number;
}) {
    const ref = useRef<HTMLDivElement>(null);

    /*
     * onClose — свежая функция на каждой перерисовке родителя. Будь она
     * в зависимостях эффекта ниже, эффект перезапускался бы на каждую
     * набранную букву и снова ставил фокус на первый элемент окна —
     * крестик: в поле формы можно было ввести только один символ.
     */
    const closeRef = useRef(onClose);
    closeRef.current = onClose;

    useEffect(() => {
        if (!open) return;

        // Кто открыл окно — туда фокус и вернётся, а не в начало страницы
        const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;

        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') closeRef.current();

            // Фокус не должен уходить на элементы под окном:
            // иначе Tab уводит в фоновую страницу и человек теряется
            if (e.key === 'Tab' && ref.current) {
                const items = ref.current.querySelectorAll<HTMLElement>(
                    'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
                );

                if (items.length === 0) return;

                const first = items[0];
                const last = items[items.length - 1];

                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        };

        document.addEventListener('keydown', onKey);
        document.body.style.overflow = 'hidden';

        // Сначала поле ввода, а не крестик в шапке: окно с формой
        // открывают, чтобы в неё писать
        (
            ref.current?.querySelector<HTMLElement>('input:not([type="file"]), select, textarea') ??
            ref.current?.querySelector<HTMLElement>('button')
        )?.focus();

        return () => {
            document.removeEventListener('keydown', onKey);
            document.body.style.overflow = '';
            if (opener?.isConnected) opener.focus();
        };
    }, [open]);

    if (!open) return null;

    return (
        <div className="overlay open" onClick={onClose} role="presentation">
            <div
                ref={ref}
                className="modal"
                style={{ maxWidth: width }}
                role="dialog"
                aria-modal="true"
                aria-label={title}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="modal-head">
                    <div>
                        <h2 className="t-h3">{title}</h2>
                        {description && <p className="t-sm muted mt-8">{description}</p>}
                    </div>
                    <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label={t('common.close')}>
                        <X aria-hidden className="size-5" />
                    </button>
                </div>

                {children && <div className="modal-body">{children}</div>}
                {footer && <div className="modal-foot">{footer}</div>}
            </div>
        </div>
    );
}
