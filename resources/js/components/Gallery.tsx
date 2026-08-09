import { useState } from 'react';
import { cn } from '@/lib/cn';

export interface GalleryImage {
    id: number;
    url: string;
    thumb: string;
}

/**
 * Галерея фотографий объявления.
 *
 * Без модального просмотра и увеличения: покупателю нужно понять,
 * что за товар, а не рассмотреть текстуру. Крупный кадр плюс лента
 * миниатюр решают это без библиотеки лайтбокса и её обработчиков.
 *
 * Лента показывается от двух фотографий: одна миниатюра под одним
 * снимком — интерфейс ради интерфейса.
 */
export function Gallery({ images, alt }: { images: GalleryImage[]; alt: string }) {
    const [active, setActive] = useState(0);
    const current = images[active] ?? images[0];

    if (!current) return null;

    return (
        <div>
            <img className="gallery-main" src={current.url} alt={alt} />

            {images.length > 1 && (
                <div className="gallery-strip" role="tablist" aria-label="Фотографии объявления">
                    {images.map((image, i) => (
                        <button
                            key={image.id}
                            type="button"
                            role="tab"
                            aria-selected={i === active}
                            aria-label={`Фотография ${i + 1} из ${images.length}`}
                            className={cn(i === active && 'is-active')}
                            onClick={() => setActive(i)}
                        >
                            <img src={image.thumb} alt="" loading="lazy" />
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
