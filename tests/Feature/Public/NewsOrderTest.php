<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\NewsPost;
use App\Support\NewsRepository;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Str;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Порядок новостей в ленте: свежие сверху.
 *
 * Новость без даты публикации разрешена, и её место зависело от базы:
 * SQLite уводит NULL вниз, PostgreSQL при сортировке по убыванию
 * поднимает наверх. На боевом Postgres лента открывалась бы новостью
 * без даты — раньше самой свежей.
 */
class NewsOrderTest extends TestCase
{
    use RefreshDatabase;

    private function entry(string $title, ?string $published, int $sort = 0): NewsPost
    {
        return NewsPost::query()->create([
            'slug' => Str::slug($title),
            'category' => 'Полезное',
            'title' => $title,
            'excerpt' => 'Коротко о деле',
            'body' => 'Текст новости.',
            'read_time' => '1 мин',
            'is_published' => true,
            'published_at' => $published,
            'sort' => $sort,
        ]);
    }

    /** @return list<string> */
    private function titles(): array
    {
        return app(NewsRepository::class)->all()->pluck('title')->all();
    }

    #[Test]
    public function свежие_новости_идут_первыми(): void
    {
        $this->entry('Позавчерашняя', now()->subDays(2)->toDateTimeString());
        $this->entry('Сегодняшняя', now()->toDateTimeString());
        $this->entry('Вчерашняя', now()->subDay()->toDateTimeString());

        $this->assertSame(['Сегодняшняя', 'Вчерашняя', 'Позавчерашняя'], $this->titles());
    }

    #[Test]
    public function новость_без_даты_уходит_в_конец(): void
    {
        $this->entry('Без даты', null);
        $this->entry('Старая', now()->subYear()->toDateTimeString());
        $this->entry('Свежая', now()->toDateTimeString());

        $this->assertSame(['Свежая', 'Старая', 'Без даты'], $this->titles());
    }

    #[Test]
    public function новости_одной_даты_стоят_в_одном_и_том_же_порядке(): void
    {
        $same = now()->subDay()->toDateTimeString();

        $this->entry('Вес ниже', $same, 1);
        $this->entry('Вес выше', $same, 5);

        $this->assertSame(['Вес выше', 'Вес ниже'], $this->titles());
        $this->assertSame($this->titles(), $this->titles());
    }

    #[Test]
    public function лента_на_странице_новостей_отсортирована(): void
    {
        $this->entry('Без даты', null);
        $this->entry('Прошлогодняя', now()->subYear()->toDateTimeString());
        $this->entry('Сегодняшняя', now()->toDateTimeString());

        $page = $this->get('/news')->assertOk()->viewData('page');

        $this->assertSame(
            ['Сегодняшняя', 'Прошлогодняя', 'Без даты'],
            array_column($page['props']['posts'], 'title'),
        );
    }
}
