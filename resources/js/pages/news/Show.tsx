import { Link } from '@/components/ui/Link';
import { ArrowLeft, CalendarDays, Clock } from 'lucide-react';
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
    body: string[];
    image: string | null;
}

export default function NewsShow({ post, related }: { post: Post; related: Post[] }) {
    return (
        <PublicLayout title={post.title} description={post.excerpt}>
            <div className="container" style={{ padding: '24px 0 96px' }}>
                <nav aria-label="Хлебные крошки" style={{ paddingBottom: 20 }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>Главная</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li>
                            <Link href={routes.news}>Новости</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            {post.category}
                        </li>
                    </ol>
                </nav>

                {/* Колонка текста ограничена по ширине: строка длиннее 75 символов
                    читается заметно хуже — глаз теряет начало следующей строки */}
                <div data-reveal style={{ maxWidth: 920, marginBottom: 32, borderRadius: "var(--r-card)", overflow: "hidden" }}>
                    <NewsCover category={post.category} image={post.image} size={72} />
                </div>

                <article style={{ maxWidth: '72ch' }}>
                    <div className="row wrap" style={{ gap: 10, marginBottom: 16 }}>
                        <span className="badge badge-supply">{post.category}</span>
                        <span className="t-caption muted row" style={{ gap: 6 }}>
                            <CalendarDays aria-hidden className="size-3.5" /> {post.date}
                        </span>
                        <span className="t-caption muted row" style={{ gap: 6 }}>
                            <Clock aria-hidden className="size-3.5" /> {post.read}
                        </span>
                    </div>

                    <h1 className="t-h1">{post.title}</h1>
                    <p className="t-lead mt-16">{post.excerpt}</p>

                    <div className="mt-32">
                        {post.body.map((p) => (
                            <p key={p} className="t-body" style={{ marginBottom: 18 }}>
                                {p}
                            </p>
                        ))}
                    </div>

                    <div className="mt-48" style={{ paddingTop: 24, borderTop: '1px solid var(--border)' }}>
                        <Link href={routes.news} className="btn btn-secondary">
                            <ArrowLeft aria-hidden className="size-4" /> Все новости
                        </Link>
                    </div>
                </article>

                {related.length > 0 && (
                    <section className="mt-48">
                        <h2 className="t-h3" style={{ marginBottom: 20 }}>
                            Читайте также
                        </h2>
                        <div className="grid grid-3">
                            {related.map((r) => (
                                <Link key={r.slug} href={routes.newsPost(r.slug)} className="card lift" style={{ padding: 0, overflow: "hidden", color: "inherit", display: "block" }}>
                                    <NewsCover category={r.category} image={r.image} size={36} />
                                    <div style={{ padding: 18 }}>
                                    <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
                                        <span className="badge badge-neutral">{r.category}</span>
                                        <span className="t-caption muted">{r.date}</span>
                                    </div>
                                    <h3 className="t-h4" style={{ marginBottom: 8 }}>{r.title}</h3>
                                    <p className="t-sm muted">{r.excerpt}</p>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </PublicLayout>
    );
}
