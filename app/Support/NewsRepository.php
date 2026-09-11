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
            'image' => $this->imageUrl($post),
            'title' => $post->title,
            'excerpt' => $post->excerpt,
            'body' => $post->paragraphs(),
        ];
    }

    /**
     * Адрес обложки новости.
     *
     * Диск указан явно. Storage::url() строит адрес по диску по умолчанию,
     * а по умолчанию в приложении стоит local — приватное хранилище вне
     * корня сайта. Адрес получался правдоподобным, но ничего по нему не
     * отдавалось: на странице оставалась пустая рамка. Обложку кладёт
     * админка на публичный диск, оттуда же её и берём — как логотипы
     * компаний и картинки из настроек.
     */
    private function imageUrl(NewsPost $post): ?string
    {
        $path = trim((string) $post->image_path);

        if ($path === '') {
            return null;
        }

        // Готовый адрес — внешняя ссылка или файл из public/ — идёт как есть
        if (str_starts_with($path, 'http://') || str_starts_with($path, 'https://') || str_starts_with($path, '/')) {
            return $path;
        }

        // Файла может не быть: загрузки времён эфемерного хранилища пропали
        // с диска. Градиент по рубрике лучше значка битой картинки.
        if (! Storage::disk('public')->exists($path)) {
            return null;
        }

        return Storage::disk('public')->url($path);
    }
}
