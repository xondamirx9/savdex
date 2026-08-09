<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\NewsPost;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Storage;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;

/**
 * Новости площадки.
 *
 * Читает из таблицы news_posts — новости редактируются из админки
 * (§6.6 ТЗ). Репозиторий остался прослойкой: контроллеры и страницы
 * работают с готовыми массивами и не знают, откуда пришли данные,
 * поэтому переезд из кода в базу их не затронул.
 */
class NewsRepository
{
    /** @return Collection<int, array<string, mixed>> */
    public function all(): Collection
    {
        return NewsPost::query()
            ->published()
            ->orderByDesc('published_at')
            ->orderByDesc('sort')
            ->get()
            ->map($this->present(...));
    }

    /** @return Collection<int, array<string, mixed>> */
    public function latest(int $limit = 3): Collection
    {
        return $this->all()->take($limit);
    }

    /** @return array<string, mixed> */
    public function find(string $slug): array
    {
        $post = NewsPost::query()->published()->where('slug', $slug)->first();

        if ($post === null) {
            throw new NotFoundHttpException;
        }

        return $this->present($post);
    }

    /** @return Collection<int, array<string, mixed>> */
    public function related(string $slug, int $limit = 3): Collection
    {
        $post = NewsPost::query()->published()->where('slug', $slug)->first();

        if ($post === null) {
            return collect();
        }

        // Сначала из той же рубрики, потом любые свежие —
        // блок «читайте также» не должен оставаться пустым
        $sameCategory = NewsPost::query()
            ->published()
            ->where('category', $post->category)
            ->where('id', '!=', $post->id)
            ->orderByDesc('published_at')
            ->limit($limit)
            ->get();

        $rest = NewsPost::query()
            ->published()
            ->where('id', '!=', $post->id)
            ->whereNotIn('id', $sameCategory->pluck('id'))
            ->orderByDesc('published_at')
            ->limit($limit)
            ->get();

        return $sameCategory->concat($rest)->take($limit)->map($this->present(...))->values();
    }

    /** @return list<string> */
    public function categories(): array
    {
        return NewsPost::query()
            ->published()
            ->select('category')
            ->distinct()
            ->orderBy('category')
            ->pluck('category')
            ->all();
    }

    /**
     * Форма ответа сохранена прежней: страницы новостей уже написаны
     * под эти ключи, и менять их ради переезда хранилища незачем.
     *
     * @return array<string, mixed>
     */
    private function present(NewsPost $post): array
    {
        return [
            'slug' => $post->slug,
            'category' => $post->category,
            'date' => $post->published_at !== null
                ? DateHelper::dayMonthYear($post->published_at)
                : '',
            'sort' => $post->sort,
            'read' => $post->readTime(),
            'image' => filled($post->image_path) ? Storage::url($post->image_path) : null,
            'title' => $post->title,
            'excerpt' => $post->excerpt,
            'body' => $post->paragraphs(),
        ];
    }
}
