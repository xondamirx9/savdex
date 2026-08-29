<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Устойчивость постранички каталога компаний.
 *
 * У свежеимпортированной сотни компаний все ключи сортировки равны
 * (без проверки, без отзывов), и без уникального хвоста Postgres
 * тасовал равных между запросами: одна карточка выпадала на двух
 * страницах подряд, другая не показывалась вовсе — «дубликаты»,
 * которых нет в базе.
 */
class PaginationStabilityTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function страницы_не_пересекаются_и_покрывают_всех(): void
    {
        // Три страницы по 12 неразличимых по сортировке компаний
        Company::factory()->count(30)->create(['verification_level' => 0, 'rating' => 0]);

        $seen = [];

        foreach ([1, 2, 3] as $page) {
            $this->get("/companies?page={$page}")
                ->assertOk()
                ->assertInertia(function (AssertableInertia $inertia) use (&$seen): void {
                    foreach ($inertia->toArray()['props']['companies']['data'] as $row) {
                        $seen[] = $row['slug'];
                    }
                });
        }

        $this->assertSame(count($seen), count(array_unique($seen)), 'карточка не должна повторяться на разных страницах');
        $this->assertCount(30, $seen, 'каждая компания обязана попасть ровно на одну страницу');
    }
}
