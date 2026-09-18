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
    public function справочники_в_админке_на_языке_площадки(): void
    {
        $this->actingAs($this->admin());

        $category = Category::factory()->named('Стройматериалы')->create();
        $category->translations()->create(['locale' => 'en', 'name' => 'Construction materials']);

        // Так выглядит сервер, где APP_LOCALE не задана
        app()->setLocale('en');

        $this->get('/admin/tenders/create')
            ->assertOk()
            ->assertSee('Стройматериалы')
            ->assertDontSee('Construction materials');

        $this->assertSame('ru', app()->getLocale());
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

    #[Test]
    public function импорт_узнаёт_категорию_в_вольном_написании(): void
    {
        $this->actingAs($this->admin());

        $metally = Category::factory()->named('Металлы')->create();
        Category::factory()->named('Чёрные металлы')->child($metally)->create();

        // «е» вместо «ё», путь из админки и неразрывный пробел из Excel
        $this->import([
            'Заголовок' => 'Поставка арматуры',
            'Категория' => "Металлы →\u{00A0}Черные металлы",
            'Ссылка на источник' => 'https://xarid.uzex.uz/lot/2',
        ]);

        $this->assertSame('Чёрные металлы', Tender::query()->firstOrFail()->category?->name());
    }

    #[Test]
    public function путь_из_двух_частей_различает_одноимённые_подкатегории(): void
    {
        $this->actingAs($this->admin());

        $stroy = Category::factory()->named('Стройматериалы')->create();
        Category::factory()->named('Другое')->child($stroy)->create();

        $mebel = Category::factory()->named('Мебель')->create();
        $mebelOther = Category::factory()->named('Другое')->child($mebel)->create();

        $this->import([
            'Заголовок' => 'Стулья для офиса',
            'Категория' => 'Мебель → Другое',
            'Ссылка на источник' => 'https://xarid.uzex.uz/lot/3',
        ]);

        $this->assertSame($mebelOther->id, Tender::query()->firstOrFail()->category_id);
    }

    /**
     * Ячейка, которую загрузка не понимает, пропускается — закупка
     * загружается. Файл на триста строк не должен отменяться из-за
     * опечатки в одной категории: пустая категория видна в списке
     * админки и правится там, потерянная закупка не видна нигде.
     */
    #[Test]
    public function незнакомая_категория_и_страна_пропускаются_а_строка_грузится(): void
    {
        $this->actingAs($this->admin());
        Category::factory()->named('Стройматериалы')->create();

        $this->import([
            'Заголовок' => 'Поставка цемента',
            'Категория' => 'Строительство',
            'Страна' => 'Мордор',
            'Почта' => '—',
            'Телефон' => 'нет данных',
            'Ссылка на источник' => 'уточняется',
            'Бюджет' => '250 000 000',
        ]);

        $tender = Tender::query()->firstOrFail();

        $this->assertSame('Поставка цемента', $tender->title);
        $this->assertNull($tender->category_id);
        $this->assertNull($tender->country_id);
        $this->assertNull($tender->contact_email);
        $this->assertNull($tender->contact_phone);
        $this->assertNull($tender->source_url);
        $this->assertSame(250000000.0, (float) $tender->budget);
    }

    #[Test]
    public function импорт_разбирает_таблицу_на_чужом_языке(): void
    {
        $this->actingAs($this->admin());

        $category = Category::factory()->named('Стройматериалы')->create();
        $category->translations()->create(['locale' => 'en', 'name' => 'Construction materials']);

        // Таблица выгружена с англоязычной площадки, а заголовки
        // набраны вперемешку — в окне импорта не угадалось ничего
        $this->import([
            'Title' => 'Cement supply for school',
            'Kategoriya' => 'Construction materials',
            'Amount' => '1,000,000',
            'Currency' => 'сум',
            'Deadline' => '30 октября 2026',
            'Link' => 'https://xarid.uzex.uz/lot/9',
            'Publish' => 'ha',
        ], mapped: false);

        $tender = Tender::query()->firstOrFail();

        $this->assertSame('Cement supply for school', $tender->title);
        $this->assertSame($category->id, $tender->category_id);
        $this->assertSame(1_000_000.0, (float) $tender->budget);
        $this->assertSame('UZS', $tender->currency);
        $this->assertSame('2026-10-30 23:59:59', $tender->deadline_at?->toDateTimeString());
        $this->assertSame(Tender::STATUS_PUBLISHED, $tender->status);
    }

    #[Test]
    public function синонимы_русских_заголовков_и_сумма_словами_читаются(): void
    {
        $this->actingAs($this->admin());

        $category = Category::factory()->named('Стройматериалы')->create();

        $this->import([
            'Наименование' => 'Поставка цемента',
            'Категория ' => 'Стройматериалы',
            'Сумма' => '250 млн',
            'Валюта' => 'сум',
            'Срок подачи' => '30.10.2026',
        ], mapped: false);

        $tender = Tender::query()->firstOrFail();

        $this->assertSame('Поставка цемента', $tender->title);
        $this->assertSame($category->id, $tender->category_id);
        $this->assertSame(250_000_000.0, (float) $tender->budget);
        $this->assertSame('UZS', $tender->currency);
        $this->assertSame('2026-10-30 23:59:59', $tender->deadline_at?->toDateTimeString());
    }

    #[Test]
    public function выгрузка_с_зарубежной_площадки_читается_целиком(): void
    {
        $this->actingAs($this->admin());

        $category = Category::factory()->named('Металлы')->create();
        $category->translations()->create(['locale' => 'en', 'name' => 'Metals']);

        // Так выглядят столбцы в выгрузках закупок: ни одного
        // совпадения с русскими подписями формы
        $this->import([
            'Tender title' => 'Permanent registration of suppliers',
            'Procuring entity' => 'ПАО «Северсталь»',
            'Sector' => 'Metals',
            'Estimated value' => 'USD 1,200,000.00',
            'Submission deadline' => '30 October 2026',
            'Tender URL' => 'https://severstal.com/tender/1',
        ], mapped: false);

        $tender = Tender::query()->firstOrFail();

        $this->assertSame('Permanent registration of suppliers', $tender->title);
        $this->assertSame('ПАО «Северсталь»', $tender->customer);
        $this->assertSame($category->id, $tender->category_id);
        $this->assertSame(1_200_000.0, (float) $tender->budget);
        $this->assertSame('2026-10-30 23:59:59', $tender->deadline_at?->toDateTimeString());
    }

    #[Test]
    public function бюджет_диапазоном_берётся_по_нижней_границе(): void
    {
        $this->actingAs($this->admin());

        $this->import([
            'Заголовок' => 'Поставка щебня',
            'Сумма контракта' => 'от 100 000 до 200 000',
        ], mapped: false);

        $this->assertSame(100_000.0, (float) Tender::query()->firstOrFail()->budget);
    }

    /**
     * Прогнать одну строку через импортёр так, как это делает
     * очередь Filament: соответствие колонок — по русским заголовкам.
     *
     * @param  array<string, string>  $row
     * @param  bool  $mapped  соответствие из окна импорта; false — то,
     *                        что Filament не угадал ни одного столбца
     */
    private function import(array $row, bool $mapped = true): void
    {
        $import = Import::create([
            'user_id' => auth()->id(),
            'file_name' => 'tenders.csv',
            'file_path' => 'tenders.csv',
            'importer' => TenderImporter::class,
            'total_rows' => 1,
        ]);

        $columnMap = [];

        if ($mapped) {
            foreach (TenderImporter::getColumns() as $column) {
                $columnMap[$column->getName()] = $column->getExampleHeader();
            }
        }

        (new TenderImporter($import, $columnMap, []))($row);
    }
}
