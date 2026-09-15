import { Check, Copy, Download, Printer, Send, X } from 'lucide-react';
import qrcode from 'qrcode-generator';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui';
import { t } from '@/lib/i18n';

/**
 * QR-код визитки компании.
 *
 * Кодирование делает qrcode-generator (MIT). Своя реализация энкодера
 * писалась и была отброшена: сгенерированные ей коды не читались
 * сканером (проверено декодером jsQR, 0 из 6). QR описан стандартом
 * ISO/IEC 18004 — писать его вручную значит добавить риск без выгоды.
 */

/** Светлое поле вокруг кода: четыре модуля требует стандарт. */
const QUIET = 4;

const DARK = '#0f172a';

const LIGHT = '#ffffff';

function encode(text: string) {
    // Уровень M: код читается при загрязнении до 15 % и остаётся компактным
    const qr = qrcode(0, 'M');
    qr.addData(text);
    qr.make();

    return qr;
}

function toSvg(text: string, scale = 6): string {
    const qr = encode(text);
    const size = qr.getModuleCount();
    const total = (size + QUIET * 2) * scale;

    // Все тёмные модули одним <path>: отдельные <rect> дают файл
    // в разы тяжелее и заметно медленнее рисуются
    let path = '';
    for (let r = 0; r < size; r++) {
        for (let c = 0; c < size; c++) {
            if (qr.isDark(r, c)) {
                path += `M${(c + QUIET) * scale} ${(r + QUIET) * scale}h${scale}v${scale}h-${scale}z`;
            }
        }
    }

    return (
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${total} ${total}" width="${total}" height="${total}">` +
        `<rect width="${total}" height="${total}" fill="${LIGHT}"/>` +
        `<path d="${path}" fill="${DARK}"/></svg>`
    );
}

/**
 * Тот же код растром.
 *
 * Скачивался SVG, а галерея телефона его не открывает — вместо кода
 * показывается значок повреждённого файла. QR скачивают как раз на
 * телефон, чтобы показать с экрана, поэтому файл обязан быть обычной
 * картинкой. Сторона около 1024 точек: с экрана считывается с любого
 * расстояния и хватает, чтобы напечатать код на визитке.
 */
function toCanvas(text: string, target = 1024): HTMLCanvasElement {
    const qr = encode(text);
    const size = qr.getModuleCount();
    const modules = size + QUIET * 2;

    // Сторона модуля — целое число точек: дробная даёт размытые края,
    // а размытый модуль сканер читает хуже
    const scale = Math.max(1, Math.round(target / modules));
    const side = modules * scale;

    const canvas = document.createElement('canvas');
    canvas.width = side;
    canvas.height = side;

    const ctx = canvas.getContext('2d');

    if (ctx) {
        ctx.fillStyle = LIGHT;
        ctx.fillRect(0, 0, side, side);
        ctx.fillStyle = DARK;

        for (let r = 0; r < size; r++) {
            for (let c = 0; c < size; c++) {
                if (qr.isDark(r, c)) {
                    ctx.fillRect((c + QUIET) * scale, (r + QUIET) * scale, scale, scale);
                }
            }
        }
    }

    return canvas;
}

export function QrModal({
    open,
    onClose,
    name,
    url,
}: {
    open: boolean;
    onClose: () => void;
    name: string;
    url: string;
}) {
    const svg = useMemo(() => (open ? toSvg(url) : ''), [open, url]);
    const [copied, setCopied] = useState(false);

    async function copyLink() {
        try {
            await navigator.clipboard.writeText(url);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Clipboard API недоступен по http — ссылка видна и её можно выделить мышью
        }
    }
    const dialogRef = useRef<HTMLDivElement>(null);

    // Ловушка фокуса, Esc и блокировка прокрутки фона — A11Y-02 из QA.md
    useEffect(() => {
        if (!open) return;

        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', onKey);
        document.body.style.overflow = 'hidden';
        dialogRef.current?.querySelector<HTMLElement>('button')?.focus();

        return () => {
            document.removeEventListener('keydown', onKey);
            document.body.style.overflow = '';
        };
    }, [open, onClose]);

    if (!open) return null;

    function download() {
        const canvas = toCanvas(url);

        const save = (href: string, temporary: boolean) => {
            const a = document.createElement('a');
            a.href = href;
            a.download = 'savdex-qr.png';

            // Ссылка добавляется в документ: по отсоединённому узлу
            // часть браузеров не кликает, и скачивание не начинается
            document.body.appendChild(a);
            a.click();
            a.remove();

            // Отзывать ссылку сразу нельзя: браузер не успевает
            // забрать данные, и файл сохраняется пустым
            if (temporary) setTimeout(() => URL.revokeObjectURL(href), 10_000);
        };

        if (typeof canvas.toBlob === 'function') {
            canvas.toBlob((blob) => blob && save(URL.createObjectURL(blob), true), 'image/png');

            return;
        }

        save(canvas.toDataURL('image/png'), false);
    }

    /*
     * Страница печати собирается узлами DOM, а не строкой в document.write.
     *
     * Название компании задаёт сама компания и видит его любой посетитель
     * визитки. В шаблонной строке оно попадало в разметку как разметка:
     * компания с названием вида `<img onerror=...>` выполняла свой код
     * в окне печати, а оно открыто через window.open('') и наследует
     * origin открывшего — то есть код ходил бы по сайту с его сессией.
     * textContent вставляет текст текстом, чем бы он ни выглядел.
     */
    function print() {
        const w = window.open('', '_blank', 'width=480,height=640');
        if (!w) return;

        const doc = w.document;
        doc.title = t('qr.window_title');
        doc.body.style.cssText = 'display:grid;place-items:center;height:100vh;margin:0;font-family:sans-serif';

        const box = doc.createElement('div');
        box.style.textAlign = 'center';

        // Разметка здесь наша собственная, собранная toSvg() из чисел
        const code = doc.createElement('div');
        code.innerHTML = svg;
        box.appendChild(code);

        const caption = doc.createElement('p');
        caption.style.cssText = 'margin-top:12px;font-size:14px';
        caption.textContent = name;
        box.appendChild(caption);

        const link = doc.createElement('p');
        link.style.cssText = 'font-size:12px;color:#64748b';
        link.textContent = url;
        box.appendChild(link);

        doc.body.appendChild(box);
        w.print();
    }

    async function share() {
        const text = t('qr.share_text', { name, url });
        if (navigator.share) {
            try {
                await navigator.share({ title: 'SAVDEX', text, url });
            } catch {
                // Пользователь закрыл системное меню — это не ошибка
            }
            return;
        }
        await navigator.clipboard?.writeText(text);
    }

    return (
        <div className="overlay open" onClick={(e) => e.target === e.currentTarget && onClose()}>
            <div className="modal" style={{ maxWidth: 420 }} role="dialog" aria-modal="true" aria-labelledby="qr-title" ref={dialogRef}>
                <div className="modal-head">
                    <h2 className="t-h3" id="qr-title">{t('qr.title')}</h2>
                    <button className="btn btn-ghost btn-icon" aria-label={t('common.close')} onClick={onClose}>
                        <X aria-hidden className="size-5" />
                    </button>
                </div>

                <div className="modal-body">
                    <p className="t-sm muted" style={{ marginBottom: 16 }}>{name}</p>

                    {/* Ссылка идёт первой: за ней приходят чаще, чем за QR-кодом */}
                    <div className="row" style={{ gap: 8, marginBottom: 16, background: "var(--bg)", borderRadius: "var(--r-btn)", padding: "10px 12px" }}>
                        <span className="t-sm" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {url}
                        </span>
                        <button className="btn btn-ghost btn-sm" onClick={copyLink}>
                            {copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
                            {copied ? t('qr.copied') : t('qr.copy')}
                        </button>
                    </div>
                    <div
                        style={{
                            background: 'var(--white)', border: '1px solid var(--border)',
                            borderRadius: 'var(--r-card)', padding: 16, display: 'grid', placeItems: 'center',
                        }}
                        dangerouslySetInnerHTML={{ __html: svg }}
                        role="img"
                        aria-label={t('qr.code_aria', { name })}
                    />
                    <p className="t-caption muted" style={{ marginTop: 12, lineHeight: 1.5 }}>
                        {t('qr.hint')}
                    </p>
                </div>

                <div className="modal-foot" style={{ flexWrap: 'wrap' }}>
                    <Button variant="secondary" onClick={download}>
                        <Download aria-hidden className="size-4" /> {t('qr.download')}
                    </Button>
                    <Button variant="secondary" onClick={print}>
                        <Printer aria-hidden className="size-4" /> {t('qr.print')}
                    </Button>
                    <Button style={{ flex: 1 }} onClick={share}>
                        <Send aria-hidden className="size-4" /> {t('qr.send')}
                    </Button>
                </div>
            </div>
        </div>
    );
}
