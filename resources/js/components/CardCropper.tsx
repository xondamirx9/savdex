import { RotateCw, ZoomIn } from 'lucide-react';
import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';

/**
 * Редактор фото визитки: рамка нужного формата, фото внутри можно
 * двигать, приближать и поворачивать на 90°.
 *
 * Обрезка делается здесь, в браузере: на сервер уходит готовый снимок
 * рамки, и визитка на странице выглядит ровно так, как в редакторе.
 * Фото всегда закрывает рамку целиком — пустых полос по краям не бывает.
 */

/** Формат рамки: ширина к высоте. Визитка 90×50 мм — 1,8. */
const RATIOS = {
    horizontal: 90 / 50,
    vertical: 50 / 90,
    square: 1,
} as const;

export type CardRatio = keyof typeof RATIOS;

/** Длинная сторона готового снимка: хватает и для экрана, и для печати. */
const OUTPUT = 1600;

const MAX_ZOOM = 4;

interface Offset {
    x: number;
    y: number;
}

export function CardCropper({
    file,
    onCancel,
    onDone,
    busy = false,
}: {
    file: File;
    onCancel: () => void;
    onDone: (blob: Blob) => void;
    busy?: boolean;
}) {
    const [image, setImage] = useState<HTMLImageElement | null>(null);
    const [ratio, setRatio] = useState<CardRatio>('horizontal');
    const [zoom, setZoom] = useState(1);
    const [rotation, setRotation] = useState(0);
    const [offset, setOffset] = useState<Offset>({ x: 0, y: 0 });
    const [frameW, setFrameW] = useState(0);
    const wrap = useRef<HTMLDivElement>(null);
    const frame = useRef<HTMLDivElement>(null);
    const drag = useRef<{ x: number; y: number; start: Offset } | null>(null);
    const zoomBy = useRef<(delta: number) => void>(() => {});

    useEffect(() => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => {
            setImage(img);
            // Снимок вертикальный — и рамку сразу предлагаем вертикальную
            setRatio(img.naturalHeight > img.naturalWidth * 1.15 ? 'vertical' : 'horizontal');
        };
        img.src = url;

        return () => URL.revokeObjectURL(url);
    }, [file]);

    // Ширина рамки — по ширине окна: на телефоне редактор не вылезает за экран
    useEffect(() => {
        const node = wrap.current;

        if (!node) return;

        const measure = () => setFrameW(Math.min(node.clientWidth, 520));
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(node);

        return () => observer.disconnect();
    }, []);

    const aspect = RATIOS[ratio];
    // Вертикальная рамка уже горизонтальной — иначе на экране она огромная
    const width = ratio === 'vertical' ? Math.round(frameW * 0.55) : frameW;
    const height = Math.round(width / aspect);
    const turned = rotation % 180 !== 0;
    const natW = image ? (turned ? image.naturalHeight : image.naturalWidth) : 1;
    const natH = image ? (turned ? image.naturalWidth : image.naturalHeight) : 1;
    // Минимальный масштаб — фото закрывает рамку целиком
    const cover = Math.max(width / natW, height / natH);
    const scale = cover * zoom;

    /** Сдвиг не даёт фото отойти от края рамки. */
    function clamp(next: Offset, nextScale = scale): Offset {
        const maxX = Math.max(0, (natW * nextScale - width) / 2);
        const maxY = Math.max(0, (natH * nextScale - height) / 2);

        return {
            x: Math.min(maxX, Math.max(-maxX, next.x)),
            y: Math.min(maxY, Math.max(-maxY, next.y)),
        };
    }

    // Новый формат или поворот — фото заново по центру
    useEffect(() => {
        setOffset({ x: 0, y: 0 });
        setZoom(1);
    }, [ratio, rotation]);

    function changeZoom(next: number) {
        const value = Math.min(MAX_ZOOM, Math.max(1, next));
        setZoom(value);
        setOffset((current) => clamp(current, cover * value));
    }

    function onPointerDown(e: PointerEvent<HTMLDivElement>) {
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { x: e.clientX, y: e.clientY, start: offset };
    }

    function onPointerMove(e: PointerEvent<HTMLDivElement>) {
        const start = drag.current;

        if (!start) return;

        setOffset(clamp({ x: start.start.x + e.clientX - start.x, y: start.start.y + e.clientY - start.y }));
    }

    zoomBy.current = (delta) => changeZoom(zoom + delta);

    /*
     * Колесо мыши масштабирует фото, а не прокручивает страницу.
     * Слушатель свой, не onWheel: у React он пассивный, и отменить
     * прокрутку из него нельзя.
     */
    useEffect(() => {
        const node = frame.current;

        if (!node) return;

        const listener = (e: globalThis.WheelEvent) => {
            e.preventDefault();
            zoomBy.current(-e.deltaY * 0.002);
        };
        node.addEventListener('wheel', listener, { passive: false });

        return () => node.removeEventListener('wheel', listener);
    }, []);

    /** Снимок рамки тем же преобразованием, что на экране, в полном размере. */
    function save() {
        if (!image || width === 0) return;

        const outW = aspect >= 1 ? OUTPUT : Math.round(OUTPUT * aspect);
        const outH = Math.round(outW / aspect);
        const k = outW / width;
        const canvas = document.createElement('canvas');
        canvas.width = outW;
        canvas.height = outH;
        const ctx = canvas.getContext('2d');

        if (!ctx) return;

        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, outW, outH);
        ctx.imageSmoothingQuality = 'high';
        ctx.translate(outW / 2 + offset.x * k, outH / 2 + offset.y * k);
        ctx.rotate((rotation * Math.PI) / 180);
        ctx.scale(scale * k, scale * k);
        ctx.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);
        canvas.toBlob((blob) => blob && onDone(blob), 'image/jpeg', 0.92);
    }

    return (
        <div ref={wrap} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <p className="t-sm muted">{t('cards.crop_hint')}</p>

            <div className="row wrap" style={{ gap: 6 }} role="group" aria-label={t('cards.ratio')}>
                {(Object.keys(RATIOS) as CardRatio[]).map((key) => (
                    <button
                        key={key}
                        type="button"
                        className={cn('chip', ratio === key && 'chip-active')}
                        aria-pressed={ratio === key}
                        onClick={() => setRatio(key)}
                    >
                        {t(`cards.ratio_${key}`)}
                    </button>
                ))}
            </div>

            <div
                ref={frame}
                className="card-cropper-frame"
                style={{ width, height }}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={() => (drag.current = null)}
                onPointerCancel={() => (drag.current = null)}
            >
                {image && (
                    <img
                        src={image.src}
                        alt=""
                        draggable={false}
                        style={{
                            position: 'absolute',
                            left: '50%',
                            top: '50%',
                            width: image.naturalWidth,
                            height: image.naturalHeight,
                            maxWidth: 'none',
                            transform: `translate(-50%, -50%) translate(${offset.x}px, ${offset.y}px) rotate(${rotation}deg) scale(${scale})`,
                            transformOrigin: 'center',
                            userSelect: 'none',
                            pointerEvents: 'none',
                        }}
                    />
                )}
            </div>

            <div className="row" style={{ gap: 10, alignItems: 'center' }}>
                <ZoomIn aria-hidden className="size-4 muted" />
                <input
                    type="range"
                    min={1}
                    max={MAX_ZOOM}
                    step={0.01}
                    value={zoom}
                    onChange={(e) => changeZoom(Number(e.target.value))}
                    aria-label={t('cards.zoom')}
                    style={{ flex: 1 }}
                />
                <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setRotation((r) => (r + 90) % 360)}
                >
                    <RotateCw aria-hidden className="size-4" /> {t('cards.rotate')}
                </button>
            </div>

            <div className="row" style={{ gap: 10, justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
                    {t('cards.cancel')}
                </button>
                <button type="button" className="btn btn-primary" onClick={save} disabled={!image || busy}>
                    {t('cards.save')}
                </button>
            </div>
        </div>
    );
}
