import { DocsNav, type DocsNavItem } from '@/components/docs/DocsNav';
import { PageBlocks, type PageCard } from '@/components/docs/PageBlocks';
import { PublicLayout } from '@/layouts/PublicLayout';

/**
 * «Помощь», «Инструкция», «Правила» — страницы с текстом из админки.
 *
 * Раньше это были разделы страницы «О компании» (/about#help и т. п.)
 * с текстом из словаря. Вёрстка та же: оглавление слева, текст справа;
 * у «Помощи» под текстом — вопросы и ответы.
 */
export default function DocPage({
    page,
    faq,
    nav,
}: {
    page: PageCard;
    faq: { question: string; answer: string }[];
    nav: DocsNavItem[];
}) {
    return (
        <PublicLayout title={page.title} description={page.lead}>
            <div className="container about-page">
                <div className="grid-docs">
                    <DocsNav items={nav} active={page.key} />

                    <div>
                        <section className="doc-section">
                            <h1 className="t-h1" style={{ marginBottom: 8 }}>
                                {page.title}
                            </h1>
                            {page.lead !== '' && (
                                <p className="t-lead" style={{ marginBottom: 24 }}>
                                    {page.lead}
                                </p>
                            )}

                            <PageBlocks blocks={page.blocks} />

                            {/* Нативный <details> вместо своего аккордеона: он доступен
                                с клавиатуры и работает без JavaScript */}
                            {faq.length > 0 && (
                                <div className={page.blocks.length > 0 ? 'mt-24' : undefined}>
                                    {faq.map((item, i) => (
                                        <details key={i} className="accordion-item">
                                            <summary className="accordion-btn" style={{ cursor: 'pointer' }}>
                                                {item.question}
                                            </summary>
                                            <div className="accordion-panel">{item.answer}</div>
                                        </details>
                                    ))}
                                </div>
                            )}
                        </section>
                    </div>
                </div>
            </div>
        </PublicLayout>
    );
}
