import { useCallback, useState } from 'react';
import { Modal } from '@/components/Modal';

interface Request {
    title: string;
    /** Что именно произойдёт и что будет потеряно */
    description?: string;
    /** Надпись на кнопке действия: «Удалить», «Отвязать», «Отменить счёт» */
    confirmLabel?: string;
    /** Красная кнопка для необратимого, обычная — для остального */
    danger?: boolean;
    onConfirm: () => void;
}

/**
 * Подтверждение действия окном площадки вместо системного confirm().
 *
 * Нативный confirm плох здесь по трём причинам, и все три заметны:
 * он рисуется браузером и выпадает из оформления; его кнопки называются
 * «ОК» и «Отмена» на языке операционной системы, а площадка работает
 * на пяти языках; браузер позволяет отключить такие окна галочкой
 * «не показывать больше» — и тогда необратимое действие выполняется
 * без вопроса вообще.
 *
 * Здесь же название действия стоит прямо на кнопке: «Удалить»
 * вместо «ОК» — человек читает кнопку, а не текст над ней.
 *
 * Использование:
 *   const { confirm, dialog } = useConfirm();
 *   <button onClick={() => confirm({ title: 'Удалить?', danger: true, onConfirm: … })} />
 *   {dialog}
 */
export function useConfirm() {
    const [request, setRequest] = useState<Request | null>(null);

    const confirm = useCallback((next: Request) => setRequest(next), []);
    const close = useCallback(() => setRequest(null), []);

    const dialog = request ? (
        <Modal open onClose={close} title={request.title} description={request.description} width={420}>
            <div className="row" style={{ gap: 10, justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={close}>
                    Отмена
                </button>
                <button
                    className={request.danger ? 'btn btn-danger' : 'btn btn-primary'}
                    onClick={() => {
                        request.onConfirm();
                        close();
                    }}
                >
                    {request.confirmLabel ?? 'Подтвердить'}
                </button>
            </div>
        </Modal>
    ) : null;

    return { confirm, dialog };
}
