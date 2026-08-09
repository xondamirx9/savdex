import { Link } from '@/components/ui/Link';
import { ArrowRight, CalendarDays, Clock } from 'lucide-react';
import { NewsCover } from '@/components/NewsCover';
import { PublicLayout } from '@/layouts/PublicLayout';
import { routes } from '@/routes';

interface Post {
    slug: string;
    category: string;
    date: string;
    read: string;
    title: string;
    excerpt: string;
    image: string | null;
}

export default function NewsIndex({ posts, categories }: { posts: Post[]; categories: string[] }) {
    const [lead, ...rest] = posts;

    return (
        <PublicLayout
            title="Новости"
            description="Новости площадки SAVDEX: обновления сервиса, изменения тарифов и аналитика рынка."
        >
            <div className="container" style={{ padding: '32px 0 96px' }}>
                <nav aria-label="Хлебные крошки" style={{ paddingBottom: 16 }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>Главная</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            Новости
                        </li>
                    </ol>
                </nav>

                <div className="section-head-left">
                    <span className="eyebrow">Блог площадки</span>
                    <h1 className="t-section">Новости</h1>
                    <p className="t-lead">Обновления площадки, изменения условий и аналитика рынка</p>
                </div>

                <div className="row wrap" style={{ gap: 8, marginBottom: 32 }}>
                    <button className="chip chip-active">Все</button>
                    {categories.map((c) => (
                        <button key={c} className="chip">
                            {c}
                        </button>
                    ))}
                </div>

                {/* Главная публикация асимметричная: обложка и текст рядом,
                    а не такая же карточка, как у остальных. Ряд одинаковых
                    прямоугольников и создаёт ощущение шаблона. */}
                {lead && (
                    <Link
                        href={routes.newsPost(lead.slug)}
                        data-reveal
                        className="card lift news-lead"
                        style={{ padding: 0, overflow: 'hidden', marginBottom: 32, color: 'inherit' }}
                    >
                        <NewsCover category={lead.category} image={lead.image} size={64} />
                        <div className="news-lead-body">
                            <div className="row wrap" style={{ gap: 10, marginBottom: 14 }}>
                                <span className="badge badge-supply">{lead.category}</span>
                                <span className="t-caption muted row" style={{ gap: 6 }}>
                                    <CalendarDays aria-hidden className="size-3.5" /> {lead.date}
                                </span>
                                <span className="t-caption muted row" style={{ gap: 6 }}>
                                    <Clock aria-hidden className="size-3.5" /> {lead.read}
                                </span>
                            </div>
                            <h2 className="t-h2" style={{ marginBottom: 12 }}>
                                {lead.title}
                            </h2>
                            <p className="t-body muted" style={{ flex: 1 }}>
                                {lead.excerpt}
                            </p>
                            <span className="row mt-24" style={{ gap: 8, color: 'var(--primary-700)', fontWeight: 600 }}>
                                Читать полностью <ArrowRight aria-hidden className="go-arrow size-4" />
                            </span>
                        </div>
                    </Link>
                )}

                <div className="grid grid-3" data-reveal-stagger>
                    {rest.map((p) => (
                        <Link
                            key={p.slug}
                            href={routes.newsPost(p.slug)}
                            className="card lift"
                            style={{
                                padding: 0,
                                overflow: 'hidden',
                                display: 'flex',
                                flexDirection: 'column',
                                color: 'inherit',
                            }}
                        >
                            <NewsCover category={p.category} image={p.image} />
                            <div style={{ padding: 18, display: 'flex', flexDirection: 'column', flex: 1 }}>
                                <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
                                    <span className="badge badge-neutral">{p.category}</span>
                                    <span className="t-caption muted">{p.date}</span>
                                </div>
                                <h3 className="t-h4" style={{ marginBottom: 8 }}>
                                    {p.title}
                                </h3>
                                <p className="t-sm muted" style={{ flex: 1 }}>
                                    {p.excerpt}
                                </p>
                                <span
                                    className="row mt-16 t-sm"
                                    style={{ gap: 6, color: 'var(--primary-700)', fontWeight: 600 }}
                                >
                                    Читать <ArrowRight aria-hidden className="go-arrow size-4" />
                                </span>
                            </div>
                        </Link>
                    ))}
                </div>
            </div>
        </PublicLayout>
    );
}
