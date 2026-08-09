import { useForm } from '@inertiajs/react';
import { useEffect } from 'react';
import { Modal } from '@/components/Modal';

/** Что можно загрузить. Порядок и подписи совпадают с CompanyDocument. */
const VERIFICATION_TYPES: Record<string, string> = {
    registration: 'Свидетельство о регистрации',
    license: 'Лицензия',
    certificate: 'Сертификат',
    quality: 'Паспорт качества',
};

const MATERIAL_TYPES: Record<string, string> = {
    presentation: 'Презентация',
    price_list: 'Прайс-лист',
    catalog: 'Каталог продукции',
    other: 'Другой файл',
};

/**
 * Загрузка файла компании.
 *
 * Документы и материалы загружаются одной формой, но ведут себя
 * по-разному: документ уходит модератору и влияет на верификацию,
 * материал сразу виден партнёрам. Разница объясняется прямо в форме —
 * иначе человек ждёт проверки прайс-листа, которой не будет.
 */
export function FileUploadModal({
    open,
    onClose,
    initialType = 'presentation',
}: {
    open: boolean;
    onClose: () => void;
    initialType?: string;
}) {
    const { data, setData, post, processing, errors, reset, progress } = useForm<{
        type: string;
        title: string;
        file: File | null;
        valid_until: string;
        is_public: boolean;
    }>({
        type: initialType,
        title: '',
        file: null,
        valid_until: '',
        is_public: true,
    });

    // Кнопка «Загрузить документ» и «Загрузить файл» открывают одну форму,
    // но с разным типом по умолчанию — иначе человек каждый раз меняет его руками
    useEffect(() => {
        if (open) setData('type', initialType);
    }, [open, initialType]);

    const isVerification = Object.hasOwn(VERIFICATION_TYPES, data.type);

    function submit() {
        post('/cabinet/company/files', {
            preserveScroll: true,
            forceFormData: true,
            onSuccess: () => {
                reset();
                onClose();
            },
        });
    }

    return (
        <Modal
            open={open}
            onClose={onClose}
            title="Загрузить файл"
            width={520}
            footer={
                <>
                    <button className="btn btn-primary" style={{ flex: 1 }} disabled={processing} onClick={submit}>
                        {processing ? `Загружаем… ${progress?.percentage ?? 0} %` : 'Загрузить'}
                    </button>
                    <button className="btn btn-ghost" onClick={onClose}>
                        Отмена
                    </button>
                </>
            }
        >
            <div className="field">
                <label className="label" htmlFor="f-type">
                    Тип файла <span className="req">*</span>
                </label>
                <select
                    id="f-type"
                    className="select"
                    value={data.type}
                    onChange={(e) => setData('type', e.target.value)}
                >
                    <optgroup label="Материалы для партнёров">
                        {Object.entries(MATERIAL_TYPES).map(([key, label]) => (
                            <option key={key} value={key}>
                                {label}
                            </option>
                        ))}
                    </optgroup>
                    <optgroup label="Документы для проверки">
                        {Object.entries(VERIFICATION_TYPES).map(([key, label]) => (
                            <option key={key} value={key}>
                                {label}
                            </option>
                        ))}
                    </optgroup>
                </select>
                <p className="hint">
                    {isVerification
                        ? 'Документ уйдёт модератору. После проверки повышает уровень верификации компании.'
                        : 'Материал появится на визитке сразу — модерация для него не нужна.'}
                </p>
            </div>

            <div className="field">
                <label className="label" htmlFor="f-title">
                    Название <span className="req">*</span>
                </label>
                <input
                    id="f-title"
                    className="input"
                    maxLength={190}
                    value={data.title}
                    onChange={(e) => setData('title', e.target.value)}
                    placeholder="Прайс-лист на цемент, июль 2026"
                />
                {errors.title && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.title}</p>}
            </div>

            <div className="field">
                <label className="label" htmlFor="f-file">
                    Файл <span className="req">*</span>
                </label>
                <input
                    id="f-file"
                    className="input"
                    type="file"
                    accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.zip"
                    onChange={(e) => setData('file', e.target.files?.[0] ?? null)}
                />
                <p className="hint">PDF, Word, Excel, презентация, изображение или ZIP. До 20 МБ.</p>
                {errors.file && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.file}</p>}
            </div>

            {/* Срок нужен только документам: у прайс-листа его не бывает,
                а лишнее поле в форме тормозит заполнение */}
            {isVerification && (
                <div className="field">
                    <label className="label" htmlFor="f-valid">
                        Действует до
                    </label>
                    <input
                        id="f-valid"
                        className="input"
                        type="date"
                        value={data.valid_until}
                        onChange={(e) => setData('valid_until', e.target.value)}
                    />
                    <p className="hint">Оставьте пустым, если срок не ограничен</p>
                    {errors.valid_until && (
                        <p className="hint" style={{ color: 'var(--danger)' }}>{errors.valid_until}</p>
                    )}
                </div>
            )}

            <label className="check">
                <input
                    type="checkbox"
                    checked={data.is_public}
                    onChange={(e) => setData('is_public', e.target.checked)}
                />
                Показывать на визитке компании
            </label>
        </Modal>
    );
}
