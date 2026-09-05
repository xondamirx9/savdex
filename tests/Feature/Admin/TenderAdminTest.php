<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Imports\TenderImporter;
use App\Filament\Resources\Tenders\Pages\CreateTender;
use App\Filament\Resources\Tenders\TenderResource;
use App\Models\Category;
use App\Models\Tender;
use App\Models\User;
use Filament\Actions\Imports\Models\Import;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Тендеры в админке: по одному через форму и массово из таблицы.
 *
 * Раздел доступен модератору — размещение закупок это работа
 * контент-менеджера, а не право суперадмина.
 */
class TenderAdminTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role = User::ADMIN_MODERATOR): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    #[Test]
    public function раздел_доступен_и_модератору_и_суперадмину(): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));
        $this->assertTrue(TenderResource::canViewAny());
        $this->get('/admin/tenders')->assertOk();

        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));
        $this->assertTrue(TenderResource::canViewAny());
    }

    #[Test]
    public function тендер_создаётся_через_форму_с_адресом_и_автором(): void
    {
        $admin = $this->admin();
        $this->actingAs($admin);

        $category = Category::factory()->named('Стройматериалы')->create();

        Livewire::test(CreateTender::class)
            ->fillForm([
                'title' => 'Поставка цемента М400 для школы',
                'description' => 'Нужно 500 тонн.',
                'customer' => 'ГУП «Тошкент шахар курилиш»',
                'category_id' => $category->id,
                'budget' => 250000000,
                'currency' => 'UZS',
                'deadline_at' => now()->addDays(20)->format('Y-m-d H:i:s'),
                'status' => Tender::STATUS_PUBLISHED,
                'published_at' => now()->format('Y-m-d H:i:s'),
            ])
            ->call('create')
            ->assertHasNoFormErrors();

        $tender = Tender::query()->firstOrFail();

        $this->assertSame('postavka-tsementa-m400-dlia-shkoly-'.$tender->id, $tender->slug);
        $this->assertSame($admin->id, $tender->author_id);
        $this->assertSame(Tender::STATUS_PUBLISHED, $tender->status);

        // Опубликованный тендер сразу виден на витрине
        $this->get('/tenders/'.$tender->slug)->assertOk();
    }

    #[Test]
    public function заголовок_обязателен(): void
    {
        $this->actingAs($this->admin());

        Livewire::test(CreateTender::class)
            ->fillForm(['title' => '', 'currency' => 'UZS', 'status' => Tender::STATUS_DRAFT])
            ->call('create')
            ->assertHasFormErrors(['title']);
    }

    #[Test]
    public function импорт_разбирает_русские_заголовки_категорию_дату_и_сумму(): void
    {
        $admin = $this->admin();
        $this->actingAs($admin);
        Category::factory()->named('Стройматериалы')->create();

        $this->import([
            'Заголовок' => 'Поставка цемента М400',
            'Описание' => 'Требуется 500 тонн.',
            'Заказчик' => 'ГУП «Тошкент шахар курилиш»',
            'Категория' => 'стройматериалы',
            'Город' => 'Ташкент',
            'Бюджет' => '250 000 000',
            'Валюта' => 'uzs',
            'Приём заявок до' => '30.10.2026',
            'Ссылка на источник' => 'https://xarid.uzex.uz/lot/1',
            'Телефон' => '+998 71 200-00-00',
            'Опубликовать' => 'да',
        ]);

        $tender = Tender::query()->firstOrFail();

        $this->assertSame('Поставка цемента М400', $tender->title);
        $this->assertSame('Стройматериалы', $tender->category?->name());
        $this->assertSame(250_000_000.0, (float) $tender->budget);
        $this->assertSame('UZS', $tender->currency);
        $this->assertSame('2026-10-30 23:59:59', $tender->deadline_at?->toDateTimeString());
        $this->assertSame(Tender::STATUS_PUBLISHED, $tender->status);
        $this->assertNotNull($tender->published_at);
        $this->assertSame($admin->id, $tender->author_id);
        $this->assertNotNull($tender->slug);
    }

    #[Test]
    public function повторный_импорт_обновляет_тендер_по_ссылке_на_источник(): void
    {
        $this->actingAs($this->admin());

        $row = [
            'Заголовок' => 'Поставка цемента',
            'Ссылка на источник' => 'https://xarid.uzex.uz/lot/1',
            'Валюта' => 'UZS',
            'Опубликовать' => 'нет',
        ];

        $this->import($row);
        $this->import([...$row, 'Заголовок' => 'Поставка цемента М400 (уточнено)']);

        $this->assertSame(1, Tender::count());
        $this->assertSame('Поставка цемента М400 (уточнено)', Tender::first()?->title);
        $this->assertSame(Tender::STATUS_DRAFT, Tender::first()?->status);
    }

    /**
     * Прогнать одну строку через импортёр так, как это делает
     * очередь Filament: соответствие колонок — по русским заголовкам.
     *
     * @param  array<string, string>  $row
     */
    private function import(array $row): void
    {
        $import = Import::create([
            'user_id' => auth()->id(),
            'file_name' => 'tenders.csv',
            'file_path' => 'tenders.csv',
            'importer' => TenderImporter::class,
            'total_rows' => 1,
        ]);

        $columnMap = [];

        foreach (TenderImporter::getColumns() as $column) {
            $columnMap[$column->getName()] = $column->getExampleHeader();
        }

        (new TenderImporter($import, $columnMap, []))($row);
    }
}
