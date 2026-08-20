import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { useSupport } from '@/lib/support';
import { routes } from '@/routes';

/**
 * Юридические документы: оферта, способы оплаты, безопасность платежей,
 * политика конфиденциальности, возвраты.
 *
 * Тексты приходят из LegalController. Раздел собирается из узлов —
 * абзацев и списков вперемешку: в оферте перечисления стоят внутри
 * пунктов, а не одним списком в конце, и разделять их на отдельные
 * блоки значило бы сбить нумерацию разделов.
 *
 * Флаг draft оставлен на случай будущих неутверждённых редакций —
 * он выводит предупреждение о том, что документ ещё не действует.
 */

interface Node {
    p?: string;
    list?: string[];
}

interface Block {
    heading: string;
    content: Node[];
}

interface Props {
    title: string;
    intro: string;
    /** Абзацы до первого нумерованного раздела: преамбула оферты. */
    preamble?: string[];
    updatedAt: string;
    draft: boolean;
    blocks: Block[];
    siblings: { href: string; label: string; current: boolean }[];
}

/** Маркер списка: точка того же цвета, что и акценты интерфейса. */
function Bullet() {
    return (
        <span
            aria-hidden
            style={{
                marginTop: 9,
                width: 5,
                height: 5,
                borderRadius: '50%',
                background: 'var(--primary-500)',
                flexShrink: 0,
            }}
        />
    );
}

export default function Legal({ title, intro, preamble, updatedAt, draft, blocks, siblings }: Props) {
    const support = useSupport();

    return (
        <PublicLayout title={title} description={intro}>
            <div className="container" style={{ padding: '32px 0 96px' }}>
                <nav aria-label="Хлебные крошки" style={{ paddingBottom: 16 }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>Главная</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            {title}
                        </li>
                    </ol>
                </nav>

                <div className="grid-docs">
                    <aside>
                        <nav className="doc-nav card" style={{ padding: 10 }} aria-label="Документы">
                            {siblings.map((s) => (
                                <Link key={s.href} href={s.href} aria-current={s.current ? 'true' : undefined}>
                                    {s.label}
                                </Link>
                            ))}
                        </nav>
                    </aside>

                    <div>
                        <h1 className="t-h1">{title}</h1>
                        <p className="t-lead mt-16">{intro}</p>

                        {draft && (
                            <div className="alert alert-warning mt-24">
                                <span aria-hidden>⚠</span>
                                <div>
                                    <b>Рабочая редакция.</b> Текст подготовлен как основа и не является
                                    публичной офертой до утверждения юристом. Итоговая редакция появится
                                    до запуска площадки.
                                </div>
                            </div>
                        )}

                        <div className="prose" style={{ maxWidth: '72ch' }}>
                            {preamble && preamble.length > 0 && (
                                <section className="mt-32">
                                    {preamble.map((p) => (
                                        <p key={p} className="t-body mt-12">
                                            {p}
                                        </p>
                                    ))}
                                </section>
                            )}

                            {blocks.map((b, i) => (
                                <section key={b.heading} className={i === 0 && !preamble?.length ? 'mt-32' : 'mt-48'}>
                                    <h2 className="t-h3" style={{ marginBottom: 14 }}>
                                        {i + 1}. {b.heading}
                                    </h2>

                                    {b.content.map((node, j) =>
                                        node.list ? (
                                            <ul key={j} className="stack-8 mt-16">
                                                {node.list.map((li) => (
                                                    <li key={li} className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
                                                        <Bullet />
                                                        <span>{li}</span>
                                                    </li>
                                                ))}
                                            </ul>
                                        ) : (
                                            <p key={j} className="t-body mt-12">
                                                {node.p}
                                            </p>
                                        ),
                                    )}
                                </section>
                            ))}
                        </div>

                        <p className="t-sm muted mt-48" style={{ paddingTop: 24, borderTop: '1px solid var(--border)' }}>
                            Редакция от {updatedAt} · Оператор: {support.legal_name}, Узбекистан ·{' '}
                            <a href={`mailto:${support.email}`}>{support.email}</a>
                        </p>
                    </div>
                </div>
            </div>
        </PublicLayout>
    );
}
