import { CheckCircle2, Shield } from 'lucide-react';

/**
 * Текст страницы из админки, разобранный на блоки на сервере
 * (App\Support\PageBody): абзацы, подзаголовки, шаги с подсказками,
 * список с галочками, предупреждение.
 *
 * Блоки — простые данные, а не HTML: вёрстку в админку не пускаем.
 */
export type PageBlock =
    | { type: 'text'; text: string }
    | { type: 'heading'; text: string }
    | { type: 'note'; title: string; text: string }
    | { type: 'steps'; items: { title: string; hint: string }[] }
    | { type: 'list'; items: string[] };

export interface PageCard {
    key: string;
    title: string;
    lead: string;
    blocks: PageBlock[];
}

function Block({ block, first }: { block: PageBlock; first: boolean }) {
    const gap = first ? undefined : block.type === 'heading' ? 'mt-32' : 'mt-16';

    switch (block.type) {
        case 'heading':
            return (
                <h3 className={`t-h4 ${gap ?? ''}`} style={{ marginBottom: 16 }}>
                    {block.text}
                </h3>
            );
        case 'note':
            return (
                <div className={`alert alert-danger ${gap ?? ''}`} style={{ marginBottom: 8 }}>
                    <Shield aria-hidden className="size-5" />
                    <div>
                        <b>{block.title}</b> {block.text}
                    </div>
                </div>
            );
        case 'steps':
            return (
                <ol className={`stack-16 ${gap ?? ''}`}>
                    {block.items.map((step, i) => (
                        <li key={i}>
                            <b>{step.title}</b>
                            {step.hint !== '' && <p className="t-sm muted mt-8">{step.hint}</p>}
                        </li>
                    ))}
                </ol>
            );
        case 'list':
            return (
                <ul className={`stack-12 ${gap ?? ''}`}>
                    {block.items.map((item, i) => (
                        <li key={i} className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
                            <CheckCircle2 aria-hidden className="text-success mt-0.5 size-5 shrink-0" />
                            <span>{item}</span>
                        </li>
                    ))}
                </ul>
            );
        default:
            return <p className={`t-body ${gap ?? ''}`}>{block.text}</p>;
    }
}

export function PageBlocks({ blocks }: { blocks: PageBlock[] }) {
    return (
        <>
            {blocks.map((block, i) => (
                <Block key={i} block={block} first={i === 0} />
            ))}
        </>
    );
}
