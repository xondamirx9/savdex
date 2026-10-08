import { Link } from '@/components/ui/Link';
import { ArrowLeft, CalendarDays, Clock, Maximize2, X } from 'lucide-react';
import { useRef } from 'react';
import { NewsCover } from '@/components/NewsCover';
import { PublicLayout } from '@/layouts/PublicLayout';
import { routes } from '@/routes';
import { t } from '@/lib/i18n';

interface Post {
    slug: string;
    // Рубрика приходит дважды: по исходной обложка выбирает
    // оформление, переведённая идёт на экран
    category: string;
    category_label: string;
    date: string;
    read: string;
    title: string;
    excerpt: string;
    body: string[];
    image: string | null;
}

export default function NewsShow({ post, related }: { post: Post; related: Post[] }) {
    const zoom = useRef<HTMLDialogElement>(null);

    return (
        <PublicLayout title={post.title} description={post.excerpt}>
            <div className="container" style={{ paddingBlock: '24px 96px' }}>
                <nav aria-label={t('news.breadcrumbs')} style={{ paddingBottom: 20 }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>{t('news.home')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li>
                            <Link href={routes.news}>{t('news.title')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            {post.category_label}
                        </li>
                    </ol>
                </nav>

                {/* Обложка и текст рядом: картинка занимает основную часть
                    ширины, описание идёт боковой колонкой и начинается
                    вровень с верхом обложки. На узком экране колонки
                    складываются: сначала картинка, потом текст. */}
                <div className="news-detail">
                    <div className="news-detail-media" data-reveal>
                        {post.image ? (
                            <>
                                {/* Снимок целиком, без рамки 16:10: на обложке
                                    бывает инфографика, и обрезанные края съедали
                                    текст. Нажатие открывает его на весь экран */}
                                <button type="button" className="news-photo" onClick={() => zoom.current?.showModal()}>
                                    <img src={post.image} alt={post.title} className="news-photo-img" />
                                    <span className="news-photo-hint">
                                        <Maximize2 aria-hidden className="size-4" /> {t('news.zoom')}
                                    </span>
                                </button>
                                {/* <dialog> сам закрывается по Esc и держит фокус
                                    внутри; нажатие в любом месте тоже закрывает */}
                                <dialog
                                    ref={zoom}
                                    className="news-zoom"
                                    aria-label={post.title}
                                    onClick={(e) => e.currentTarget.close()}
                                >
                                    <img src={post.image} alt={post.title} className="news-zoom-img" />
                                    <button type="button" className="news-zoom-close" aria-label={t('common.close')}>
                                        <X aria-hidden className="size-5" />
                                    </button>
                                </dialog>
                            </>
                        ) : (
                            <NewsCover category={post.category} image={null} size={72} />
                        )}
                    </div>

                    <article className="news-detail-body">
                        <div className="row wrap" style={{ gap: 10, marginBottom: 16 }}>
                            <span className="badge badge-supply">{post.category_label}</span>
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
                            {/* pre-line сохраняет переносы внутри абзаца: редактор
                                разбивает текст пустой строкой, но одиночный перенос
                                в списке или адресе тоже осмысленный */}
                            {post.body.map((p, i) => (
                                <p key={i} className="t-body" style={{ marginBottom: 18, whiteSpace: 'pre-line' }}>
                                    {p}
                                </p>
                            ))}
                        </div>

                        <div className="mt-48" style={{ paddingTop: 24, borderTop: '1px solid var(--border)' }}>
                            <Link href={routes.news} className="btn btn-secondary">
                                <ArrowLeft aria-hidden className="size-4" /> {t('news.back')}
                            </Link>
                        </div>
                    </article>
                </div>

                {related.length > 0 && (
                    <section className="mt-48">
                        <h2 className="t-h3" style={{ marginBottom: 20 }}>
                            {t('news.related')}
                        </h2>
                        <div className="grid grid-3">
                            {related.map((r) => (
                                <Link key={r.slug} href={routes.newsPost(r.slug)} className="card lift" style={{ padding: 0, overflow: "hidden", color: "inherit", display: "block" }}>
                                    <NewsCover category={r.category} image={r.image} size={36} />
                                    <div style={{ padding: 18 }}>
                                    <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
                                        <span className="badge badge-neutral">{r.category_label}</span>
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
