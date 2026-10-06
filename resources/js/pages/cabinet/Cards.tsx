import { router, useForm } from '@inertiajs/react';
import { Camera, ExternalLink, IdCard, PenLine, Plus, QrCode, Trash2 } from 'lucide-react';
import { useRef, useState, type FormEvent } from 'react';
import { BusinessCard, type CardData } from '@/components/BusinessCard';
import { CardCropper } from '@/components/CardCropper';
import { Empty, Panel } from '@/components/cabinet';
import { FieldError } from '@/components/FieldError';
import { Modal } from '@/components/Modal';
import { QrModal } from '@/components/QrModal';
import { useConfirm } from '@/components/useConfirm';
import { TextInput } from '@/components/ui';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

interface CardRow extends CardData {
    id: number;
    url: string;
    views: number;
}

interface Fields {
    company_name: string;
    full_name: string;
    email: string;
    phone: string;
}

interface Props {
    hasCompany: boolean;
    cards: CardRow[];
    limit: number;
    defaults: Fields;
}

type Step = 'choose' | 'photo' | 'generated';

/**
 * Кабинет → «Визитки»: свои визитки, у каждой — QR-код.
 *
 * Новая визитка — фото бумажной (с редактором обрезки) или собранная
 * из четырёх полей. Поля заполнены из профиля: обычно поправить
 * нужно разве что должность в имени или рабочий телефон.
 */
export default function Cards({ hasCompany, cards, limit, defaults }: Props) {
    const [step, setStep] = useState<Step | null>(null);
    const [file, setFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [qr, setQr] = useState<CardRow | null>(null);
    const fileInput = useRef<HTMLInputElement>(null);
    const { confirm, dialog } = useConfirm();
    const form = useForm<Fields & { kind: 'generated' }>({ ...defaults, kind: 'generated' });

    const full = cards.length >= limit;

    function close() {
        setStep(null);
        setFile(null);
        form.clearErrors();
    }

    function upload(blob: Blob) {
        setUploading(true);
        router.post(
            routes.cabinetCards,
            { kind: 'photo', photo: new File([blob], 'card.jpg', { type: 'image/jpeg' }) },
            {
                forceFormData: true,
                preserveScroll: true,
                onSuccess: () => close(),
                onFinish: () => setUploading(false),
            },
        );
    }

    function create(e: FormEvent) {
        e.preventDefault();
        form.post(routes.cabinetCards, { preserveScroll: true, onSuccess: () => close() });
    }

    function remove(card: CardRow) {
        confirm({
            title: t('cards.delete_title'),
            description: t('cards.delete_text'),
            confirmLabel: t('cards.delete'),
            danger: true,
            onConfirm: () => router.delete(routes.cabinetCard(card.id), { preserveScroll: true }),
        });
    }

    const addButton = hasCompany ? (
        <button type="button" className="btn btn-primary" onClick={() => setStep('choose')} disabled={full}>
            <Plus aria-hidden className="size-4" /> {t('cards.add')}
        </button>
    ) : undefined;

    return (
        <CabinetLayout title={t('cards.title')} heading={t('cards.title')} subheading={t('cards.lead')} actions={addButton}>
            {!hasCompany ? (
                <Empty
                    icon={IdCard}
                    title={t('cards.empty_title')}
                    text={t('cards.need_company')}
                    action={{ href: routes.cabinetCompany, label: t('cabinet.nav.company') }}
                />
            ) : cards.length === 0 ? (
                <div className="card empty">
                    <div className="empty-icon">
                        <IdCard aria-hidden className="size-7" />
                    </div>
                    <p className="t-h4">{t('cards.empty_title')}</p>
                    <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 16px' }}>
                        {t('cards.empty_text')}
                    </p>
                    <button type="button" className="btn btn-primary" onClick={() => setStep('choose')}>
                        <Plus aria-hidden className="size-4" /> {t('cards.add')}
                    </button>
                </div>
            ) : (
                <Panel>
                    {full && <p className="t-sm muted" style={{ marginBottom: 14 }}>{t('cards.limit_reached', { count: limit })}</p>}
                    <div className="biz-card-grid">
                        {cards.map((card) => (
                            <div key={card.id} className="biz-card-item">
                                <div className={card.kind === 'photo' ? 'biz-card-item-photo' : undefined}>
                                    <BusinessCard card={card} />
                                </div>
                                <div className="row wrap" style={{ gap: 8 }}>
                                    <button type="button" className="btn btn-primary btn-sm" onClick={() => setQr(card)}>
                                        <QrCode aria-hidden className="size-4" /> {t('cards.qr')}
                                    </button>
                                    <a href={card.url} target="_blank" rel="noopener" className="btn btn-secondary btn-sm">
                                        <ExternalLink aria-hidden className="size-4" /> {t('cards.open')}
                                    </a>
                                    <button
                                        type="button"
                                        className="btn btn-ghost btn-sm"
                                        onClick={() => remove(card)}
                                        aria-label={t('cards.delete')}
                                    >
                                        <Trash2 aria-hidden className="size-4" />
                                    </button>
                                </div>
                                <span className="t-caption muted">{t('cards.views', { count: card.views })}</span>
                            </div>
                        ))}
                    </div>
                </Panel>
            )}

            <input
                ref={fileInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                hidden
                onChange={(e) => {
                    const chosen = e.target.files?.[0];
                    e.target.value = '';

                    if (chosen) {
                        setFile(chosen);
                        setStep('photo');
                    }
                }}
            />

            <Modal
                open={step !== null}
                onClose={close}
                title={step === 'generated' ? t('cards.kind_generated') : step === 'photo' ? t('cards.kind_photo') : t('cards.add')}
                width={step === 'choose' ? 560 : 600}
            >
                {step === 'choose' && (
                    <div className="biz-card-kinds">
                        <button type="button" className="biz-card-kind" onClick={() => fileInput.current?.click()}>
                            <Camera aria-hidden className="size-6" style={{ color: 'var(--primary-700)' }} />
                            <b>{t('cards.kind_photo')}</b>
                            <span className="t-sm muted">{t('cards.kind_photo_desc')}</span>
                        </button>
                        <button type="button" className="biz-card-kind" onClick={() => setStep('generated')}>
                            <PenLine aria-hidden className="size-6" style={{ color: 'var(--primary-700)' }} />
                            <b>{t('cards.kind_generated')}</b>
                            <span className="t-sm muted">{t('cards.kind_generated_desc')}</span>
                        </button>
                    </div>
                )}

                {step === 'photo' && file && (
                    <>
                        <CardCropper file={file} onCancel={close} onDone={upload} busy={uploading} />
                        <FieldError name="photo" />
                        <button
                            type="button"
                            className="btn btn-ghost btn-sm mt-8"
                            onClick={() => fileInput.current?.click()}
                            disabled={uploading}
                        >
                            {t('cards.change_photo')}
                        </button>
                    </>
                )}

                {step === 'generated' && (
                    <form onSubmit={create} className="space-y-4" noValidate>
                        <TextInput
                            label={t('cards.company_name')}
                            required
                            value={form.data.company_name}
                            onChange={(e) => form.setData('company_name', e.target.value)}
                            error={form.errors.company_name}
                            maxLength={190}
                        />
                        <TextInput
                            label={t('cards.full_name')}
                            required
                            autoComplete="name"
                            value={form.data.full_name}
                            onChange={(e) => form.setData('full_name', e.target.value)}
                            error={form.errors.full_name}
                            maxLength={190}
                        />
                        <TextInput
                            label={t('cards.email')}
                            type="email"
                            required
                            autoCapitalize="none"
                            spellCheck={false}
                            value={form.data.email}
                            onChange={(e) => form.setData('email', e.target.value)}
                            error={form.errors.email}
                            maxLength={190}
                        />
                        <TextInput
                            label={t('cards.phone')}
                            type="tel"
                            required
                            value={form.data.phone}
                            onChange={(e) => form.setData('phone', e.target.value)}
                            error={form.errors.phone}
                        />

                        <div>
                            <span className="label">{t('cards.preview')}</span>
                            <BusinessCard card={{ ...form.data, kind: 'generated', image: null }} />
                        </div>

                        <div className="row" style={{ gap: 10, justifyContent: 'flex-end' }}>
                            <button type="button" className="btn btn-secondary" onClick={close}>
                                {t('cards.cancel')}
                            </button>
                            <button type="submit" className="btn btn-primary" disabled={form.processing}>
                                {t('cards.save')}
                            </button>
                        </div>
                    </form>
                )}
            </Modal>

            {qr && (
                <QrModal
                    open
                    onClose={() => setQr(null)}
                    name={qr.full_name ?? qr.company_name ?? defaults.company_name}
                    url={qr.url}
                    hint={t('cards.qr_hint')}
                />
            )}

            {dialog}
        </CabinetLayout>
    );
}
