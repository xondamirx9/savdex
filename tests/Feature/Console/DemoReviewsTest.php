<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use App\Models\Company;
use App\Models\Review;
use Database\Seeders\CabinetDemoSeeder;
use Database\Seeders\DatabaseSeeder;
use Database\Seeders\DemoSeeder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Демо-отзывы не попадают к настоящим компаниям.
 *
 * Демо-сидер брал автором отзыва любую компанию базы, и на живом
 * сайте у настоящих фирм появлялись одинаковые выдуманные отзывы.
 * Миграция их скрывает, а сидер больше так не делает.
 */
class DemoReviewsTest extends TestCase
{
    use RefreshDatabase;

    private const SEEDED = 'Заказывали 60 тонн М400. Отгрузили день в день, паспорт качества приложили без напоминаний. Работаем дальше.';

    #[Test]
    public function миграция_скрывает_отзывы_сидера_и_пересчитывает_рейтинг(): void
    {
        $company = Company::factory()->create();
        $seeded = Review::factory()->count(3)->create([
            'company_id' => $company->id,
            'body' => self::SEEDED,
            'rating' => 5,
            'status' => 'published',
        ]);
        $real = Review::factory()->create(['company_id' => $company->id, 'rating' => 2, 'status' => 'published']);

        $this->assertSame(4, $company->fresh()->reviews_count);

        $migration = require database_path('migrations/2026_09_29_110000_hide_demo_seeded_reviews.php');
        $migration->up();

        foreach ($seeded as $review) {
            $this->assertSame('hidden', $review->fresh()->status);
            $this->assertNotNull($review->fresh()->moderator_note);
        }

        $this->assertSame('published', $real->fresh()->status);
        $this->assertSame(1, $company->fresh()->reviews_count);
    }

    #[Test]
    public function сидер_пишет_отзывы_только_от_демо_компаний(): void
    {
        $this->seed(DatabaseSeeder::class);
        $this->seed(DemoSeeder::class);
        $stroybaza = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $outsider = Company::factory()->create(['name' => 'ООО «Настоящая фирма»']);

        $this->seed(CabinetDemoSeeder::class);

        $authors = Review::query()->where('company_id', $stroybaza->id)->pluck('author_company_id');
        $this->assertNotContains($outsider->id, $authors->all());
        $this->assertTrue(Company::whereIn('id', $authors)->get()->every(
            fn (Company $c): bool => str_starts_with($c->name, 'ООО «Демо-'),
        ));
    }

    #[Test]
    public function на_боевой_площадке_сидер_отзывов_не_пишет(): void
    {
        $this->seed(DatabaseSeeder::class);
        $this->seed(DemoSeeder::class);
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $this->app['env'] = 'production';

        // Напрямую, а не через db:seed: тот на боевой площадке спрашивает
        // подтверждение. Модели без защиты — как их запускает db:seed
        Model::unguarded(fn () => app(CabinetDemoSeeder::class)->setContainer(app())->__invoke());

        $this->assertSame(0, Review::count());
    }
}
