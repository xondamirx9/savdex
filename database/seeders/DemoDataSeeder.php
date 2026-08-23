<?php

declare(strict_types=1);

namespace Database\Seeders;

use Illuminate\Database\Seeder;

/**
 * Демонстрационные данные для локальной разработки и показа.
 *
 * Вынесено из DatabaseSeeder намеренно: здесь создаются выдуманные
 * компании с фальшивыми рейтингами и учётные записи с паролями из
 * переменных окружения. На боевом сервере ничего этого быть не должно,
 * а `php artisan db:seed` там запускают именно для справочников.
 *
 * Запуск: php artisan db:seed --class=DemoDataSeeder
 */
class DemoDataSeeder extends Seeder
{
    public function run(): void
    {
        if (app()->isProduction()) {
            $this->command?->error('Демо-данные на боевом сервере не создаются.');

            return;
        }

        $this->call([
            DemoSeeder::class,
            CabinetDemoSeeder::class,
            // Витрина: описания компаниям и картинки объявлениям без фото
            ShowcaseSeeder::class,
        ]);
    }
}
