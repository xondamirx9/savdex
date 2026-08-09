<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Support\NewsRepository;
use App\Support\Seo;
use Inertia\Inertia;
use Inertia\Response;

class NewsController extends Controller
{
    public function __construct(private readonly NewsRepository $news) {}

    public function index(): Response
    {
        app(Seo::class)
            ->title('Новости площадки и рынка')
            ->description('Обновления SAVDEX, разборы условий поставки и новости оптового рынка Узбекистана.')
            ->canonical(url('/news'));

        return Inertia::render('news/Index', [
            'posts' => $this->news->all(),
            'categories' => $this->news->categories(),
        ]);
    }

    public function show(string $slug): Response
    {
        $post = $this->news->find($slug);

        /*
         * Разметка Article нужна не ради красоты: без неё новость
         * в выдаче стоит без даты, а дата у новости — половина смысла.
         */
        app(Seo::class)
            ->title($post['title'] ?? 'Новость')
            ->description($post['excerpt'] ?? null)
            ->canonical(url('/news/'.$slug))
            ->image($post['cover'] ?? null)
            ->type('article')
            ->schema(array_filter([
                '@type' => 'NewsArticle',
                'headline' => $post['title'] ?? null,
                'description' => $post['excerpt'] ?? null,
                'datePublished' => $post['published_at_iso'] ?? null,
                'author' => ['@type' => 'Organization', 'name' => 'SAVDEX'],
                'mainEntityOfPage' => url('/news/'.$slug),
            ]));

        return Inertia::render('news/Show', [
            'post' => $post,
            'related' => $this->news->related($slug),
        ]);
    }
}
