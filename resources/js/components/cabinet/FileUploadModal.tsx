import { useForm } from '@inertiajs/react';
import { useEffect } from 'react';
import { Modal } from '@/components/Modal';
import { t } from '@/lib/i18n';

/**
 * Что можно загрузить. Порядок и ключи совпадают с CompanyDocument,
 * подписи берутся из словаря: список рисуется на языке сайта.
 */
const VERIFICATION_TYPES = ['registration', 'license', 'certificate', 'quality'];

const MATERIAL_TYPES = ['presentation', 'price_list', 'catalog', 'other'];

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

    const isVerification = VERIFICATION_TYPES.includes(data.type);

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
            title={t('cabinet.files.modal_title')}
            width={520}
            footer={
                <>
                    <button className="btn btn-primary" style={{ flex: 1 }} disabled={processing} onClick={submit}>
                        {processing
                            ? t('cabinet.files.uploading', { percent: progress?.percentage ?? 0 })
                            : t('cabinet.files.upload')}
                    </button>
                    <button className="btn btn-ghost" onClick={onClose}>
                        {t('common.cancel')}
                    </button>
                </>
            }
        >
            <div className="field">
                <label className="label" htmlFor="f-type">
                    {t('cabinet.files.type')} <span className="req">*</span>
                </label>
                {/* Нативный список: пункты разбиты на группы <optgroup>,
                    а SelectField групп не умеет — плоский перечень из
                    материалов и документов вперемешку читался бы хуже */}
                <select
                    id="f-type"
                    className="select"
                    value={data.type}
                    onChange={(e) => setData('type', e.target.value)}
                >
                    <optgroup label={t('cabinet.files.group_materials')}>
                        {MATERIAL_TYPES.map((key) => (
                            <option key={key} value={key}>
                                {t(`cabinet.files.types.${key}`)}
                            </option>
                        ))}
                    </optgroup>
                    <optgroup label={t('cabinet.files.group_documents')}>
                        {VERIFICATION_TYPES.map((key) => (
                            <option key={key} value={key}>
                                {t(`cabinet.files.types.${key}`)}
                            </option>
                        ))}
                    </optgroup>
                </select>
                <p className="hint">
                    {isVerification ? t('cabinet.files.hint_document') : t('cabinet.files.hint_material')}
                </p>
            </div>

            <div className="field">
                <label className="label" htmlFor="f-title">
                    {t('cabinet.files.name')} <span className="req">*</span>
                </label>
                <input
                    id="f-title"
                    className="input"
                    maxLength={190}
                    value={data.title}
                    onChange={(e) => setData('title', e.target.value)}
                    placeholder={t('cabinet.files.name_placeholder')}
                />
                {errors.title && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.title}</p>}
            </div>

            <div className="field">
                <label className="label" htmlFor="f-file">
                    {t('cabinet.files.file')} <span className="req">*</span>
                </label>
                <input
                    id="f-file"
                    className="input"
                    type="file"
                    accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.zip"
                    onChange={(e) => setData('file', e.target.files?.[0] ?? null)}
                />
                <p className="hint">{t('cabinet.files.formats')}</p>
                {errors.file && <p className="hint" style={{ color: 'var(--danger)' }}>{errors.file}</p>}
            </div>

            {/* Срок нужен только документам: у прайс-листа его не бывает,
                а лишнее поле в форме тормозит заполнение */}
            {isVerification && (
                <div className="field">
                    <label className="label" htmlFor="f-valid">
                        {t('cabinet.files.valid_until')}
                    </label>
                    <input
                        id="f-valid"
                        className="input"
                        type="date"
                        value={data.valid_until}
                        onChange={(e) => setData('valid_until', e.target.value)}
                    />
                    <p className="hint">{t('cabinet.files.valid_until_hint')}</p>
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
                {t('cabinet.files.public')}
            </label>
        </Modal>
    );
}
