import type { ReactNode } from 'react';

/**
 * Мини-разметка для текстов, которые пишут компании: описание профиля
 * и подобные поля.
 *
 * Ровно две конструкции — **жирный** и списки строками на «- » или
 * «• ». Не markdown: ссылки, картинки и HTML здесь не нужны, а каждый
 * лишний синтаксис — это способ изуродовать чужую визитку. Эмодзи
 * (✔, ★ и любые другие) — обычные символы, им разметка не требуется.
 *
 * Текст безопасен по построению: собирается из React-узлов, ни одной
 * вставки сырого HTML.
 */
export function renderRichText(text: string): ReactNode {
    const blocks: ReactNode[] = [];
    let list: string[] = [];
    let paragraph: string[] = [];

    const flushList = () => {
        if (list.length > 0) {
            blocks.push(
                <ul key={`l${blocks.length}`}>
                    {list.map((item, i) => (
                        <li key={i}>{bold(item)}</li>
                    ))}
                </ul>,
            );
            list = [];
        }
    };

    const flushParagraph = () => {
        if (paragraph.length > 0) {
            blocks.push(
                <p key={`p${blocks.length}`}>
                    {paragraph.map((line, i) => (
                        <span key={i}>
                            {i > 0 && <br />}
                            {bold(line)}
                        </span>
                    ))}
                </p>,
            );
            paragraph = [];
        }
    };

    for (const raw of text.split('\n')) {
        const line = raw.trimEnd();
        const marker = /^[-•]\s+(.*)$/.exec(line.trim());

        if (marker) {
            flushParagraph();
            list.push(marker[1]);
        } else if (line.trim() === '') {
            flushList();
            flushParagraph();
        } else {
            flushList();
            paragraph.push(line);
        }
    }

    flushList();
    flushParagraph();

    return blocks;
}

/** **выделенное** → <b>; непарные звёздочки остаются текстом. */
function bold(line: string): ReactNode {
    const parts = line.split(/\*\*(.+?)\*\*/g);

    if (parts.length === 1) {
        return line;
    }

    // split с группой чередует обычные и выделенные куски: нечётные — жирные
    return parts.map((part, i) => (i % 2 === 1 ? <b key={i}>{part}</b> : part));
}
