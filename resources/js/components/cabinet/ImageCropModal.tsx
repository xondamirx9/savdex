import { Minus, Plus } from 'lucide-react';
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { Modal } from '@/components/Modal';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';

/** Во сколько раз можно приблизить сверх «фото целиком закрывает рамку». */
const MAX_ZOOM = 5;

/** Отступ рамки от краёв окна: за ним видно, что останется за кадром. */
const PAD_X = 24;

/** У узкой полосы обложки над и под рамкой видно больше — иначе не понять, что в кадр не попало. */
const PAD_Y_WIDE = 48;

/** Квадрат не растягивается во всё окно: на широком экране он был бы выше экрана ноутбука. */
const MAX_SQUARE = 340;

/** Обложка на телефоне: 120 пикселей высоты на ширину экрана — видна середина кадра. */
const PHONE_ASPECT = 343 / 120;

/** Больше по стороне холст не создаётся: iOS отказывает холстам больше ~16 Мп. */
const MAX_CANVAS = 4096;

export interface CropOutput {
    /** Ширина к высоте: 1 — квадрат логотипа, 6 — полоса обложки. */
    aspect: number;
    /** Ширина готового кадра; мелкое фото до неё не растягивается. */
    width: number;
    /** PNG сохраняет прозрачность логотипа, JPEG — лёгкий файл для фото. */
    type: 'image/png' | 'image/jpeg';
}

interface View {
    zoom: number;
    /** Точка фото (в пикселях оригинала), которая стоит в центре рамки. */
    x: number;
    y: number;
}

/**
 * Кадрирование картинки перед загрузкой — как в Telegram, только
 * рамка не круглая, а по форме места, где картинка показывается.
 *
 * Раньше файл уходил на сервер как есть, а визитка показывала его
 * середину (background-size: cover): у обложки отрезало то, ради
 * чего её снимали, логотип с полями по краям выходил крошечным.
 * Теперь человек сам двигает фото в рамке и приближает его, а на
 * сервер уходит только то, что в рамке. Сервер ничего не режет —
 * готовый кадр он лишь уменьшает и пересохраняет в WebP.
 *
 * Фото двигается мышью и пальцем, приближается ползунком, колесом
 * и щипком; с клавиатуры — стрелками и «+»/«−».
 */
export function ImageCropModal({
    file,
    output,
    title,
    hint,
    busy = false,
    onCancel,
    onConfirm,
}: {
    /** Выбранный файл; null — окно закрыто. */
    file: File | null;
    output: CropOutput;
    title: string;
    hint?: string;
    /** Кадр уже отправлен и ещё грузится. */
    busy?: boolean;
    onCancel: () => void;
    onConfirm: (cropped: File) => void;
}) {
    const [image, setImage] = useState<{ url: string; width: number; height: number } | null>(null);
    const [failed, setFailed] = useState(false);
    const [view, setView] = useState<View>({ zoom: 1, x: 0, y: 0 });
    const [stageWidth, setStageWidth] = useState(0);
    const [dragging, setDragging] = useState(false);
    const [rendering, setRendering] = useState(false);

    const stage = useRef<HTMLDivElement>(null);
    const picture = useRef<HTMLImageElement>(null);
    const pointers = useRef(new Map<number, { x: number; y: number }>());

    // Картинка читается из файла прямо в браузере: показать её
    // и вырезать кадр можно до того, как что-то уйдёт на сервер
    useEffect(() => {
        setImage(null);
        setFailed(false);

        if (!file) return;

        const url = URL.createObjectURL(file);
        const probe = new Image();

        probe.onload = () => {
            setImage({ url, width: probe.naturalWidth, height: probe.naturalHeight });
            setView({ zoom: 1, x: probe.naturalWidth / 2, y: probe.naturalHeight / 2 });
        };
        probe.onerror = () => setFailed(true);
        probe.src = url;

        return () => URL.revokeObjectURL(url);
    }, [file]);

    // Рамка считается от ширины окна: на телефоне окно — во весь экран
    useLayoutEffect(() => {
        const el = stage.current;
        if (!el) return;

        setStageWidth(el.clientWidth);

        const observer = new ResizeObserver(() => setStageWidth(el.clientWidth));
        observer.observe(el);

        return () => observer.disconnect();
    }, [image]);

    const square = output.aspect === 1;
    const frameW = Math.max(0, square ? Math.min(stageWidth - PAD_X * 2, MAX_SQUARE) : stageWidth - PAD_X * 2);
    const frameH = frameW / output.aspect;
    const frameTop = square ? PAD_X : PAD_Y_WIDE;
    const frameLeft = (stageWidth - frameW) / 2;

    /** Масштаб, при котором фото ровно закрывает рамку: меньше — по краям пусто. */
    const cover = image ? Math.max(frameW / image.width, frameH / image.height) : 1;

    /** Фото не уходит из рамки: пустых полос в кадре не бывает. */
    function clamp(next: View): View {
        if (!image || frameW === 0) return next;

        const zoom = Math.min(Math.max(next.zoom, 1), MAX_ZOOM);
        const halfW = frameW / (cover * zoom) / 2;
        const halfH = frameH / (cover * zoom) / 2;

        return {
            zoom,
            x: Math.min(Math.max(next.x, halfW), image.width - halfW),
            y: Math.min(Math.max(next.y, halfH), image.height - halfH),
        };
    }

    const current = clamp(view);
    const scale = cover * current.zoom;

    /*
     * Изменения — через функцию от прошлого вида, а не от current:
     * за один кадр браузер присылает несколько движений пальца,
     * и каждое должно сложиться с предыдущим, а не затереть его.
     */

    /** Сдвиг на экранные пиксели: фото едет за пальцем. */
    function pan(dx: number, dy: number) {
        setView((v) => {
            const from = clamp(v);
            const s = cover * from.zoom;

            return clamp({ ...from, x: from.x - dx / s, y: from.y - dy / s });
        });
    }

    /**
     * Приближение вокруг точки рамки — под курсором, между пальцами,
     * в центре для ползунка: то, что под ней, остаётся на месте.
     */
    function zoom(to: (zoom: number) => number, fx = frameW / 2, fy = frameH / 2) {
        setView((v) => {
            const from = clamp(v);
            const next = Math.min(Math.max(to(from.zoom), 1), MAX_ZOOM);
            const before = cover * from.zoom;
            const after = cover * next;
            const px = from.x + (fx - frameW / 2) / before;
            const py = from.y + (fy - frameH / 2) / before;

            return clamp({ zoom: next, x: px - (fx - frameW / 2) / after, y: py - (fy - frameH / 2) / after });
        });
    }

    /** Точка экрана в координатах рамки. */
    function inFrame(clientX: number, clientY: number) {
        const box = stage.current!.getBoundingClientRect();

        return { x: clientX - box.left - frameLeft, y: clientY - box.top - frameTop };
    }

    function onPointerDown(e: PointerEvent<HTMLDivElement>) {
        if (!image) return;

        // Первое касание — прежние точно отпущены: потерянный pointerup
        // иначе превратил бы следующее касание одним пальцем в щипок
        if (e.isPrimary) pointers.current.clear();

        e.currentTarget.setPointerCapture(e.pointerId);
        pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
        setDragging(true);
    }

    function onPointerMove(e: PointerEvent<HTMLDivElement>) {
        const previous = pointers.current.get(e.pointerId);
        if (!previous) return;

        const other = [...pointers.current.entries()].find(([id]) => id !== e.pointerId)?.[1];
        pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });

        if (!other) {
            pan(e.clientX - previous.x, e.clientY - previous.y);

            return;
        }

        // Щипок: расстояние между пальцами — масштаб, середина между
        // ними — точка, вокруг которой он идёт и за которой едет фото
        const before = Math.hypot(previous.x - other.x, previous.y - other.y);
        const after = Math.hypot(e.clientX - other.x, e.clientY - other.y);
        const mid = inFrame((e.clientX + other.x) / 2, (e.clientY + other.y) / 2);

        if (before > 0) zoom((z) => z * (after / before), mid.x, mid.y);
        pan((e.clientX - previous.x) / 2, (e.clientY - previous.y) / 2);
    }

    function onPointerUp(e: PointerEvent<HTMLDivElement>) {
        pointers.current.delete(e.pointerId);
        if (pointers.current.size === 0) setDragging(false);
    }

    // Колесо — через addEventListener: обработчик React пассивный,
    // и без preventDefault колесо заодно прокручивало бы окно
    const onWheel = useRef<(e: WheelEvent) => void>(() => {});
    onWheel.current = (e: WheelEvent) => {
        e.preventDefault();
        const point = inFrame(e.clientX, e.clientY);
        zoom((z) => z * Math.exp(-e.deltaY * 0.0015), point.x, point.y);
    };

    useEffect(() => {
        const el = stage.current;
        if (!el) return;

        const listener = (e: WheelEvent) => onWheel.current(e);
        el.addEventListener('wheel', listener, { passive: false });

        return () => el.removeEventListener('wheel', listener);
    }, [image]);

    function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
        // Стрелка двигает фото, как палец: «влево» — фото едет влево
        const step = e.shiftKey ? 40 : 10;
        const moves: Record<string, [number, number]> = {
            ArrowLeft: [-step, 0],
            ArrowRight: [step, 0],
            ArrowUp: [0, -step],
            ArrowDown: [0, step],
        };

        if (moves[e.key]) {
            e.preventDefault();
            pan(...moves[e.key]);
        } else if (e.key === '+' || e.key === '=') {
            e.preventDefault();
            zoom((z) => z * 1.2);
        } else if (e.key === '-') {
            e.preventDefault();
            zoom((z) => z / 1.2);
        }
    }

    async function save() {
        if (!image || !picture.current || !file) return;

        setRendering(true);

        try {
            const blob = await crop(
                picture.current,
                {
                    x: current.x - frameW / scale / 2,
                    y: current.y - frameH / scale / 2,
                    width: frameW / scale,
                    height: frameH / scale,
                },
                output,
            );

            const name = file.name.replace(/\.[^.]+$/, '') || 'image';
            const extension = output.type === 'image/png' ? 'png' : 'jpg';

            onConfirm(new File([blob], `${name}.${extension}`, { type: output.type }));
        } catch {
            setFailed(true);
        } finally {
            setRendering(false);
        }
    }

    const phoneW = Math.min(frameW, frameH * PHONE_ASPECT);

    return (
        <Modal
            open={file !== null}
            onClose={busy ? () => {} : onCancel}
            title={title}
            description={failed ? undefined : t('cabinet.crop.description')}
            width={560}
            footer={
                <>
                    <button
                        type="button"
                        className="btn btn-primary"
                        style={{ flex: 1 }}
                        disabled={!image || failed || busy || rendering}
                        onClick={save}
                    >
                        {busy || rendering ? t('cabinet.photos.uploading') : t('common.save')}
                    </button>
                    <button type="button" className="btn btn-ghost" disabled={busy} onClick={onCancel}>
                        {t('common.cancel')}
                    </button>
                </>
            }
        >
            {failed ? (
                <p className="error-text" role="alert">
                    {t('messages.image.unreadable')}
                </p>
            ) : (
                <>
                    <div
                        ref={stage}
                        className={cn('crop-stage', dragging && 'is-dragging')}
                        style={{ height: image ? frameH + frameTop * 2 : 240 }}
                        tabIndex={0}
                        role="application"
                        aria-label={t('cabinet.crop.stage_label')}
                        onPointerDown={onPointerDown}
                        onPointerMove={onPointerMove}
                        onPointerUp={onPointerUp}
                        onPointerCancel={onPointerUp}
                        onKeyDown={onKeyDown}
                    >
                        {image && frameW > 0 && (
                            <>
                                <img
                                    ref={picture}
                                    src={image.url}
                                    alt=""
                                    draggable={false}
                                    className="crop-image"
                                    style={{
                                        width: image.width * scale,
                                        height: image.height * scale,
                                        transform: `translate(${frameLeft + frameW / 2 - current.x * scale}px, ${frameTop + frameH / 2 - current.y * scale}px)`,
                                    }}
                                />
                                <div
                                    className={cn('crop-frame', square && 'is-square')}
                                    style={{ left: frameLeft, top: frameTop, width: frameW, height: frameH }}
                                >
                                    {/* Сетка третей — пока фото двигают, как в редакторе Telegram */}
                                    <span className="crop-grid" aria-hidden />
                                    {!square && phoneW < frameW - 1 && (
                                        <span className="crop-phone" style={{ width: phoneW }} aria-hidden />
                                    )}
                                </div>
                            </>
                        )}
                    </div>

                    <div className="crop-zoom">
                        <button
                            type="button"
                            className="btn btn-ghost btn-icon btn-sm"
                            aria-label={t('cabinet.crop.zoom_out')}
                            disabled={!image || current.zoom <= 1}
                            onClick={() => zoom((z) => z / 1.25)}
                        >
                            <Minus aria-hidden className="size-4" />
                        </button>
                        <input
                            type="range"
                            min={1}
                            max={MAX_ZOOM}
                            step={0.01}
                            value={current.zoom}
                            disabled={!image}
                            aria-label={t('cabinet.crop.zoom')}
                            onChange={(e) => {
                                const value = Number(e.target.value);
                                zoom(() => value);
                            }}
                        />
                        <button
                            type="button"
                            className="btn btn-ghost btn-icon btn-sm"
                            aria-label={t('cabinet.crop.zoom_in')}
                            disabled={!image || current.zoom >= MAX_ZOOM}
                            onClick={() => zoom((z) => z * 1.25)}
                        >
                            <Plus aria-hidden className="size-4" />
                        </button>
                    </div>

                    {hint && <p className="hint">{hint}</p>}
                </>
            )}
        </Modal>
    );
}

/**
 * Вырезать кадр из оригинала и уменьшить до нужной ширины.
 *
 * Уменьшение идёт ступенями по половине: один шаг с 4000 пикселей
 * до 512 в Safari и Firefox даёт «лесенку» на тонких буквах
 * логотипа — браузер берёт в расчёт не все пиксели оригинала.
 */
async function crop(
    source: HTMLImageElement,
    area: { x: number; y: number; width: number; height: number },
    output: CropOutput,
): Promise<Blob> {
    const width = Math.max(1, Math.round(Math.min(output.width, area.width)));
    const height = Math.max(1, Math.round(width / output.aspect));

    // Первый холст — кадр в разрешении оригинала, но не больше предела
    const fit = Math.min(1, MAX_CANVAS / Math.max(area.width, area.height));
    let canvas = draw(
        Math.max(width, Math.round(area.width * fit)),
        Math.max(height, Math.round(area.height * fit)),
        source,
        area,
        output.type,
    );

    while (canvas.width / 2 > width) {
        canvas = draw(Math.round(canvas.width / 2), Math.round(canvas.height / 2), canvas, null, output.type);
    }

    if (canvas.width !== width || canvas.height !== height) {
        canvas = draw(width, height, canvas, null, output.type);
    }

    const result = canvas;

    return new Promise((resolve, reject) =>
        result.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('toBlob'))), output.type, 0.92),
    );
}

/** Новый холст с картинкой (или её частью area), вписанной во весь холст. */
function draw(
    width: number,
    height: number,
    source: HTMLImageElement | HTMLCanvasElement,
    area: { x: number; y: number; width: number; height: number } | null,
    type: CropOutput['type'],
): HTMLCanvasElement {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d')!;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    // У JPEG нет прозрачности: без подложки прозрачный PNG стал бы чёрным
    if (type === 'image/jpeg') {
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, width, height);
    }

    const { x, y, width: w, height: h } = area ?? { x: 0, y: 0, width: source.width, height: source.height };
    ctx.drawImage(source, x, y, w, h, 0, 0, width, height);

    return canvas;
}
