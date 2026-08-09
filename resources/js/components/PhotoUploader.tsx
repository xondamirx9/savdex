import { router } from '@inertiajs/react';
import { Image as ImageIcon, Star, Trash2, Upload } from 'lucide-react';
import { useRef, useState } from 'react';
import { useConfirm } from '@/components/useConfirm';

export interface ListingPhoto {
    id: number;
    thumb: string;
}

/**
 * Фотографии объявления.
 *
 * Загрузка сразу, а не вместе с публикацией: черновик живёт в базе
 * с первого шага, и фото к нему прикрепляется тем же порядком. Ждать
 * отправки формы, чтобы узнать, что файл не подошёл, — худший момент
 * для такой новости.
 *
 * Обложка — первая по порядку, отдельного флага нет. «Сделать
 * обложкой» переставляет фотографию в начало.
 */
export function PhotoUploader({
    listingId,
    photos,
    max = 10,
}: {
    listingId: number;
    photos: ListingPhoto[];
    max?: number;
}) {
    const input = useRef<HTMLInputElement>(null);
    const { confirm, dialog } = useConfirm();
    const [busy, setBusy] = useState(false);
    const free = max - photos.length;

    function upload(files: FileList | null) {
        if (!files?.length) return;

        setBusy(true);
        router.post(
            `/cabinet/listings/${listingId}/images`,
            { images: Array.from(files) },
            {
                preserveScroll: true,
                forceFormData: true,
                onFinish: () => {
                    setBusy(false);
                    // Иначе повторный выбор того же файла не вызовет change
                    if (input.current) input.current.value = '';
                },
            },
        );
    }

    return (
        <div>
            {dialog}

            <div className="row-between wrap" style={{ gap: 12, marginBottom: 16 }}>
                <div>
                    <h3 className="t-h4">Фотографии</h3>
                    <p className="t-sm muted mt-8">
                        Первая — обложка в каталоге. Объявления с фото открывают заметно чаще.
                    </p>
                </div>
                <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busy || free <= 0}
                    onClick={() => input.current?.click()}
                >
                    <Upload aria-hidden className="size-4" />
                    {busy ? 'Загружаем…' : free > 0 ? `Добавить (осталось ${free})` : 'Больше нельзя'}
                </button>
                <input
                    ref={input}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    multiple
                    hidden
                    onChange={(e) => upload(e.target.files)}
                />
            </div>

            {photos.length === 0 ? (
                <div className="card empty" style={{ padding: '40px 24px' }}>
                    <div className="empty-icon">
                        <ImageIcon aria-hidden className="size-7" />
                    </div>
                    <p className="t-h4">Фотографий пока нет</p>
                    <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                        Объявление можно опубликовать и без них, но карточка без фото в каталоге
                        проигрывает соседним. JPG, PNG или WebP, до 8 МБ каждая.
                    </p>
                </div>
            ) : (
                <div className="photo-grid">
                    {photos.map((p, i) => (
                        <figure key={p.id} className="photo-tile">
                            <img src={p.thumb} alt={`Фотография ${i + 1}`} loading="lazy" />

                            {i === 0 && <figcaption className="photo-cover">Обложка</figcaption>}

                            <div className="photo-actions">
                                {i > 0 && (
                                    <button
                                        type="button"
                                        className="btn btn-secondary btn-icon btn-sm"
                                        title="Сделать обложкой"
                                        aria-label={`Сделать обложкой фотографию ${i + 1}`}
                                        onClick={() =>
                                            router.post(
                                                `/cabinet/listings/${listingId}/images/${p.id}/cover`,
                                                {},
                                                { preserveScroll: true },
                                            )
                                        }
                                    >
                                        <Star aria-hidden className="size-4" />
                                    </button>
                                )}
                                <button
                                    type="button"
                                    className="btn btn-danger btn-icon btn-sm"
                                    title="Удалить"
                                    aria-label={`Удалить фотографию ${i + 1}`}
                                    onClick={() =>
                                        confirm({
                                            title: 'Удалить фотографию?',
                                            description:
                                                i === 0 && photos.length > 1
                                                    ? 'Это обложка — в каталоге её заменит следующая фотография.'
                                                    : 'Файл будет удалён безвозвратно.',
                                            confirmLabel: 'Удалить',
                                            danger: true,
                                            onConfirm: () =>
                                                router.delete(
                                                    `/cabinet/listings/${listingId}/images/${p.id}`,
                                                    { preserveScroll: true },
                                                ),
                                        })
                                    }
                                >
                                    <Trash2 aria-hidden className="size-4" />
                                </button>
                            </div>
                        </figure>
                    ))}
                </div>
            )}
        </div>
    );
}
