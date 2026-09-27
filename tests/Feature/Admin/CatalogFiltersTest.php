<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Categories\Pages\ListCategories;
use App\Models\Category;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Forms\Components\Select;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Фильтры справочников говорят по-русски.
 *
 * В фильтре «Раздел» стоял список слагов: «stroymaterialy»,
 * «gotovaya-odezhda». Человек, который ищет «Стройматериалы»,
 * в таком списке их не находит — а именно за этим фильтр и открывают.
 *
 * Фильтр стран в городах переехал вместе с городами на Python —
 * проверяется в python/tests/test_cities_admin.py.
 */
class CatalogFiltersTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Варианты фильтра так, как их увидит человек: подписи строит
     * поле формы, а не сам фильтр.
     *
     * @param  class-string  $page
     * @return array<int|string, string>
     */
    private function filterOptions(string $page, string $filter): array
    {
        $form = Livewire::test($page)->instance()->getTableFiltersForm();

        foreach ($form->getFlatComponents() as $component) {
            if ($component instanceof Select
                && str_contains((string) $component->getStatePath(), $filter)) {
                return $component->getOptions() ?? [];
            }
        }

        $this->fail("фильтр «{$filter}» не найден в форме");
    }

    private function superadmin(): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => AdminAccess::SUPERADMIN,
            'status' => 'active',
        ]);
    }

    #[Test]
    public function фильтр_разделов_показывает_названия_а_не_слаги(): void
    {
        $this->actingAs($this->superadmin());

        $parent = Category::factory()->named('Стройматериалы')->create();
        Category::factory()->named('Цемент и бетон')->child($parent)->create();

        $options = $this->filterOptions(ListCategories::class, 'parent_id');

        $this->assertSame(['Стройматериалы'], array_values($options));
        $this->assertArrayHasKey($parent->id, $options);
    }

    /** Подкатегория родителем быть не может — в списке её нет. */
    #[Test]
    public function в_фильтре_только_верхний_уровень(): void
    {
        $this->actingAs($this->superadmin());

        $parent = Category::factory()->named('Металлы')->create();
        $child = Category::factory()->named('Чёрные металлы')->child($parent)->create();

        $options = $this->filterOptions(ListCategories::class, 'parent_id');

        $this->assertArrayNotHasKey($child->id, $options);
    }
}
