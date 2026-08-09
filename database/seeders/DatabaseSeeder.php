<?php

declare(strict_types=1);

namespace Database\Seeders;

use Illuminate\Database\Seeder;

/**
 * Справочники и содержимое сайта — то, что нужно любому окружению.
 *
 * Демо-данные сюда не входят намеренно: `php artisan db:seed` на боевом
 * сервере не должен создавать выдуманные компании с фальшивыми отзывами
 * и аккаунт с паролем из репозитория. Для локальной разработки есть
 * отдельный сценарий — `db:seed --class=DemoDataSeeder`.
 *
 * WithoutModelEvents не используется: Company проставляет slug в хуке
 * creating, и без событий сидер падает на NOT NULL.
 */
class DatabaseSeeder extends Seeder
{
    public function run(): void
    {
        $this->call([
            GeoSeeder::class,
            PlanSeeder::class,
            CategorySeeder::class,
            PromotionTypeSeeder::class,
            CmsSeeder::class,
        ]);
    }
}
