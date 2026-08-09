import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { routes } from '@/routes';

/**
 * Юридические документы: оферта, политика конфиденциальности, возвраты.
 *
 * Тексты — рабочая заготовка, а не итоговая редакция. Финальные формулировки
 * готовит юрист заказчика (спринт 6 по SPRINTS.md, §17 п.12 ТЗ). Пометка
 * об этом выводится на странице: документ без утверждения юристом
 * не должен выглядеть как утверждённый.
 */

interface Block {
    heading: string;
    paragraphs: string[];
    list?: string[];
}

interface Props {
    title: string;
    intro: string;
    updatedAt: string;
    draft: boolean;
    blocks: Block[];
    siblings: { href: string; label: string; current: boolean }[];
}

export default function Legal({ title, intro, updatedAt, draft, blocks, siblings }: Props) {
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
                            {blocks.map((b, i) => (
                                <section key={b.heading} className={i === 0 ? 'mt-32' : 'mt-48'}>
                                    <h2 className="t-h3" style={{ marginBottom: 14 }}>
                                        {i + 1}. {b.heading}
                                    </h2>
                                    {b.paragraphs.map((p) => (
                                        <p key={p} className="t-body mt-12">
                                            {p}
                                        </p>
                                    ))}
                                    {b.list && (
                                        <ul className="stack-8 mt-16">
                                            {b.list.map((li) => (
                                                <li key={li} className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
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
                                                    <span>{li}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </section>
                            ))}
                        </div>

                        <p className="t-sm muted mt-48" style={{ paddingTop: 24, borderTop: '1px solid var(--border)' }}>
                            Редакция от {updatedAt} · Оператор: ООО «ANJIR-GROUP», Узбекистан ·{' '}
                            <a href="mailto:support@savdex.uz">support@savdex.uz</a>
                        </p>
                    </div>
                </div>
            </div>
        </PublicLayout>
    );
}
