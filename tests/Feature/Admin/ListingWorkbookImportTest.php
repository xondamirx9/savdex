<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Listings\Pages\ListListings;
use App\Models\Category;
use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Models\Listing;
use App\Models\User;
use App\Services\ListingWorkbookImport;
use App\Support\ListingWorkbookTemplate;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;
use OpenSpout\Common\Entity\Row;
use OpenSpout\Writer\XLSX\Writer;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;
use ZipArchive;

/**
 * Загрузка каталога книгой Excel вместе с фотографиями.
 *
 * Книга собирается здесь же, а не лежит файлом в fixtures: важно,
 * чтобы тест ломался при изменении разбора, а не при пересохранении
 * фикстуры в другой версии Excel.
 *
 * Книга — до пяти листов, по одному на язык: русский главный,
 * остальные дают тексты строка к строке.
 */
class ListingWorkbookImportTest extends TestCase
{
    use RefreshDatabase;

    private const HEADERS = ['Номер', 'Название', 'Компания', 'Категория', 'Цена', 'Валюта', 'Город', 'Фото'];

    /** Шапка языкового листа: только переводимые поля. */
    private const TEXT_HEADERS = ['Заголовок', 'Описание', 'Условия поставки', 'Условия оплаты'];

    protected function setUp(): void
    {
        parent::setUp();

        Storage::fake('public');
    }

    #[Test]
    public function фотографии_достаются_объявлениям_своих_строк(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $brick = Listing::factory()->for($company)->create(['title' => 'Кирпич керамический М150']);
        $yarn = Listing::factory()->for($company)->create(['title' => 'Пряжа хлопковая 30/1']);

        // Между товарами пустая строка: номера строк не должны сползти
        $workbook = $this->workbook(
            rows: [
                2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', ''],
                3 => [],
                4 => ['', 'Пряжа хлопковая 30/1', 'ООО «Стройбаза»', '', '', '', '', ''],
            ],
            pictures: [2 => 1, 4 => 1],
        );

        $result = $this->import($workbook);

        $this->assertSame(2, $result['photos']);
        $this->assertSame(1, $brick->images()->count());
        $this->assertSame(1, $yarn->images()->count());

        Storage::disk('public')->assertExists($brick->images()->first()->path);
        Storage::disk('public')->assertExists($brick->images()->first()->thumb_path);
    }

    #[Test]
    public function несколько_фотографий_строки_идут_по_порядку_колонок(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $listing = Listing::factory()->for($company)->create(['title' => 'Кирпич керамический М150']);

        $workbook = $this->workbook(
            rows: [2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', '']],
            pictures: [2 => 3],
        );

        $this->import($workbook);

        $this->assertSame(3, $listing->images()->count());
        $this->assertSame([0, 1, 2], $listing->images()->pluck('sort')->all());
    }

    #[Test]
    public function новый_товар_создаётся_с_компанией_категорией_и_ценой(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        Category::factory()->named('Стройматериалы')->create();

        $workbook = $this->workbook(
            rows: [2 => ['', 'Профнастил С8', 'ООО «Стройбаза»', 'Стройматериалы', '1 200 000', 'сум', '', '']],
            pictures: [2 => 1],
        );

        $result = $this->import($workbook);

        $listing = Listing::query()->where('title', 'Профнастил С8')->firstOrFail();

        $this->assertSame(1, $result['created']);
        $this->assertSame('Стройматериалы', $listing->category?->name());
        $this->assertSame(1_200_000.0, (float) $listing->price);
        $this->assertSame('UZS', $listing->currency);
        $this->assertNotNull($listing->slug);
        $this->assertSame(1, $listing->images()->count());

        // Новое ждёт проверки: публикует администратор, посмотрев,
        // что получилось. Срок публикации поставит он же
        $this->assertSame(Listing::STATUS_MODERATION, $listing->status);
        $this->assertNull($listing->published_at);
        $this->assertSame(Listing::SOURCE_IMPORT, $listing->source);
    }

    #[Test]
    public function повторная_загрузка_не_плодит_фотографии(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $listing = Listing::factory()->for($company)->create(['title' => 'Кирпич керамический М150']);

        $rows = [2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', '']];

        $this->import($this->workbook($rows, [2 => 1]));
        $second = $this->import($this->workbook($rows, [2 => 1]));

        $this->assertSame(0, $second['photos']);
        $this->assertSame(1, $listing->images()->count());
    }

    #[Test]
    public function галочка_замены_меняет_фотографии(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $listing = Listing::factory()->for($company)->create(['title' => 'Кирпич керамический М150']);

        $rows = [2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', '']];

        $this->import($this->workbook($rows, [2 => 1]));
        $old = $listing->images()->first()->path;

        $this->import($this->workbook($rows, [2 => 2]), replace: true);

        $this->assertSame(2, $listing->images()->count());
        $this->assertNotContains($old, $listing->images()->pluck('path')->all());
        Storage::disk('public')->assertMissing($old);
    }

    #[Test]
    public function незнакомая_категория_останавливает_строку_с_причиной(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        $workbook = $this->workbook(
            rows: [2 => ['', 'Профнастил С8', 'ООО «Стройбаза»', 'Строительство', '', '', '', '']],
            pictures: [],
        );

        $result = $this->import($workbook);

        $this->assertSame(0, $result['created']);
        $this->assertCount(1, $result['errors']);
        $this->assertStringContainsString('Строка 2', $result['errors'][0]);
        $this->assertStringContainsString('Строительство', $result['errors'][0]);
    }

    #[Test]
    public function строка_с_номером_правит_существующее_объявление(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $listing = Listing::factory()->for($company)->create(['title' => 'Старое название', 'price' => 100]);

        $workbook = $this->workbook(
            rows: [2 => [(string) $listing->id, 'Кирпич керамический М150', '', '', '250000', '', '', '']],
            pictures: [],
        );

        $result = $this->import($workbook);

        $this->assertSame(1, $result['updated']);
        $this->assertSame('Кирпич керамический М150', $listing->fresh()->title);
        $this->assertSame(250_000.0, (float) $listing->fresh()->price);

        // Опубликованное повторная загрузка не снимает с витрины
        $this->assertSame(Listing::STATUS_ACTIVE, $listing->fresh()->status);
        $this->assertSame(Listing::SOURCE_IMPORT, $listing->fresh()->source);
    }

    #[Test]
    public function кнопка_в_админке_принимает_книгу_и_раскладывает_фотографии(): void
    {
        $admin = User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);

        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $listing = Listing::factory()->for($company)->create(['title' => 'Кирпич керамический М150']);

        $workbook = $this->workbook(
            rows: [2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', '']],
            pictures: [2 => 1],
        );

        Livewire::actingAs($admin)
            ->test(ListListings::class)
            ->callAction(TestAction::make('importWorkbook')->table(), [
                'workbooks' => [
                    UploadedFile::fake()->createWithContent('catalog.xlsx', (string) file_get_contents($workbook)),
                ],
            ])
            ->assertHasNoActionErrors();

        $this->assertSame(1, $listing->images()->count());
    }

    #[Test]
    public function за_раз_принимается_несколько_книг(): void
    {
        $admin = User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);

        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $brick = Listing::factory()->for($company)->create(['title' => 'Кирпич керамический М150']);
        $yarn = Listing::factory()->for($company)->create(['title' => 'Пряжа хлопковая 30/1']);

        // Каталог разрезан по разделам: в каждой книге свой товар
        $first = $this->workbook([2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', '']], [2 => 1]);
        $second = $this->workbook([2 => ['', 'Пряжа хлопковая 30/1', 'ООО «Стройбаза»', '', '', '', '', '']], [2 => 1]);

        Livewire::actingAs($admin)
            ->test(ListListings::class)
            ->callAction(TestAction::make('importWorkbook')->table(), [
                'workbooks' => [
                    UploadedFile::fake()->createWithContent('stroy.xlsx', (string) file_get_contents($first)),
                    UploadedFile::fake()->createWithContent('tekstil.xlsx', (string) file_get_contents($second)),
                ],
            ])
            ->assertHasNoActionErrors();

        $this->assertSame(1, $brick->images()->count());
        $this->assertSame(1, $yarn->images()->count());
    }

    #[Test]
    public function образец_книги_загружается_без_правок(): void
    {
        // Образец мы отдаём заказчику: если его же загрузка не читает,
        // читать нечего и файлу, собранному по образцу
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $section = Category::factory()->named('Стройматериалы')->create();
        Category::factory()->named('Кирпич и блоки')->child($section)->create();
        $this->city('Ташкент');

        $path = tempnam(sys_get_temp_dir(), 'savdex-template').'.xlsx';
        ListingWorkbookTemplate::write($path);

        $result = $this->import($path);

        $listing = Listing::query()->where('title', 'Кирпич керамический М150')->firstOrFail();

        $this->assertSame([], $result['errors']);
        $this->assertSame([], $result['notes']);
        $this->assertSame(1, $result['created']);
        $this->assertSame('Кирпич и блоки', $listing->category?->name());
        $this->assertSame('Ташкент', $listing->city?->name());
        $this->assertSame('UZS', $listing->currency);
        $this->assertSame(1_200.0, (float) $listing->price);
        $this->assertSame(Listing::STATUS_MODERATION, $listing->status);
        $this->assertSame('Самовывоз со склада, доставка по Ташкентской области.', $listing->delivery_terms);
        $this->assertSame('Предоплата 50 %, остаток по факту отгрузки.', $listing->payment_terms);

        // Четыре языковых листа образца дают четыре перевода каждого поля
        foreach (['en', 'uz', 'zh', 'tr'] as $locale) {
            $this->assertTrue($listing->hasTranslation('title', $locale), $locale);
            $this->assertTrue($listing->hasTranslation('description', $locale), $locale);
            $this->assertTrue($listing->hasTranslation('delivery_terms', $locale), $locale);
            $this->assertTrue($listing->hasTranslation('payment_terms', $locale), $locale);
        }

        $this->assertSame('Ceramic brick M150', $listing->localizedTitle('en'));
    }

    #[Test]
    public function столбцы_на_любом_языке_узнаются(): void
    {
        // Каждый столбец назван на своём языке, значения — тоже
        Company::factory()->create(['name' => 'Uyut Gulistan Mebel']);

        $furniture = Category::factory()->named('Мебель')->create();
        $furniture->translations()->create(['locale' => 'zh', 'name' => '家具']);

        $city = $this->city('Ташкент');
        $city->translations()->create(['locale' => 'uz', 'name' => 'Toshkent']);

        $path = tempnam(sys_get_temp_dir(), 'savdex-test').'.xlsx';

        $writer = new Writer;
        $writer->openToFile($path);
        $writer->addRow(Row::fromValues(['Nomi', 'Şirket', '类别', 'Price', 'Валюта', 'Shahar', 'Yayınla']));
        $writer->addRow(Row::fromValues([
            'Ofis stoli', 'Uyut Gulistan Mebel', '家具', '1 200 000', "so'm", 'Toshkent', 'evet',
        ]));
        $writer->close();

        $result = $this->import($path);

        $listing = Listing::query()->where('title', 'Ofis stoli')->firstOrFail();

        $this->assertSame([], $result['errors']);
        $this->assertSame(1, $result['created']);
        $this->assertSame('Мебель', $listing->category?->name());
        $this->assertSame($city->id, $listing->city_id);
        $this->assertSame(1_200_000.0, (float) $listing->price);
        $this->assertSame('UZS', $listing->currency);
        $this->assertSame(Listing::STATUS_MODERATION, $listing->status);
    }

    // ── Языковые листы ──────────────────────────────────────────

    #[Test]
    public function языковые_листы_дают_переводы_строка_к_строке(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        // Два товара через пустую строку: смещение от шапки должно
        // сходиться на всех листах, включая пустые строки
        $workbook = $this->workbook(
            rows: [
                2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', ''],
                3 => [],
                4 => ['', 'Пряжа хлопковая 30/1', 'ООО «Стройбаза»', '', '', '', '', ''],
            ],
            pictures: [2 => 1],
            translations: [
                'English' => [
                    2 => ['Ceramic brick M150', 'Solid brick.', 'Pick-up from the warehouse', '50 % prepayment'],
                    3 => [],
                    4 => ['Cotton yarn 30/1', 'Combed yarn.', '', ''],
                ],
                '中文' => [
                    2 => ['M150 陶瓷砖', '实心砖。', '仓库自提', '预付 50 %'],
                    3 => [],
                    4 => ['棉纱 30/1', '', '', ''],
                ],
            ],
        );

        $result = $this->import($workbook);

        $this->assertSame([], $result['errors']);
        $this->assertSame(2, $result['created']);

        $brick = Listing::query()->where('title', 'Кирпич керамический М150')->firstOrFail();
        $yarn = Listing::query()->where('title', 'Пряжа хлопковая 30/1')->firstOrFail();

        $this->assertSame('Ceramic brick M150', $brick->localizedTitle('en'));
        $this->assertSame('Solid brick.', $brick->localizedDescription('en'));
        $this->assertSame('Pick-up from the warehouse', $brick->localizedDeliveryTerms('en'));
        $this->assertSame('50 % prepayment', $brick->localizedPaymentTerms('en'));
        $this->assertSame('M150 陶瓷砖', $brick->localizedTitle('zh'));
        $this->assertSame(1, $brick->images()->count());

        $this->assertSame('Cotton yarn 30/1', $yarn->localizedTitle('en'));
        $this->assertSame('棉纱 30/1', $yarn->localizedTitle('zh'));

        // Чего на листе не было, того и в переводах нет
        $this->assertFalse($yarn->hasTranslation('description', 'zh'));
        $this->assertFalse($yarn->hasTranslation('delivery_terms', 'en'));
        $this->assertFalse($brick->hasTranslation('title', 'uz'));
    }

    #[Test]
    public function русский_лист_узнаётся_по_имени_а_не_по_порядку(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $listing = Listing::factory()->for($company)->create(['title' => 'Кирпич керамический М150']);

        // Английский лист первый: цены и фото всё равно должны
        // читаться с русского, а английский — только тексты
        $workbook = $this->workbook(
            rows: [2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '9 900', 'сум', '', '']],
            pictures: [2 => 1],
            translations: ['English' => [2 => ['Ceramic brick M150', '', '', '']]],
            russianLast: true,
        );

        $result = $this->import($workbook);

        $this->assertSame([], $result['errors']);
        $this->assertSame(1, $result['updated']);
        $this->assertSame(1, $listing->images()->count());
        $this->assertSame(9_900.0, (float) $listing->fresh()->price);
        $this->assertSame('Ceramic brick M150', $listing->fresh()->localizedTitle('en'));
    }

    #[Test]
    public function лист_с_другим_числом_строк_отклоняет_книгу(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        // На английском листе строка удалена: переводы съехали бы
        // на соседний товар, и никто бы этого не заметил
        $workbook = $this->workbook(
            rows: [
                2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', ''],
                3 => ['', 'Пряжа хлопковая 30/1', 'ООО «Стройбаза»', '', '', '', '', ''],
            ],
            pictures: [],
            translations: ['English' => [2 => ['Cotton yarn 30/1', '', '', '']]],
        );

        $result = $this->import($workbook);

        $this->assertSame(0, $result['created']);
        $this->assertSame(0, $result['rows']);
        $this->assertCount(1, $result['errors']);
        $this->assertStringContainsString('English', $result['errors'][0]);
        $this->assertStringContainsString('не загружена', $result['errors'][0]);
        $this->assertSame(0, Listing::query()->count());
    }

    #[Test]
    public function пустой_языковой_лист_не_мешает_загрузке(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        $workbook = $this->workbook(
            rows: [2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', '']],
            pictures: [],
            translations: ['English' => []],
        );

        $result = $this->import($workbook);

        $this->assertSame([], $result['errors']);
        $this->assertSame(1, $result['created']);
        $this->assertCount(1, $result['notes']);
        $this->assertStringContainsString('English', $result['notes'][0]);

        $listing = Listing::query()->firstOrFail();
        $this->assertFalse($listing->hasTranslation('title', 'en'));
    }

    #[Test]
    public function пустая_ячейка_перевода_не_стирает_старый(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $listing = Listing::factory()->for($company)->create([
            'title' => 'Кирпич керамический М150',
            'title_i18n' => ['en' => 'Ceramic brick M150', 'tr' => 'Seramik tuğla M150'],
        ]);

        // Переводчик дошёл только до описания: заголовок в книге пуст
        $workbook = $this->workbook(
            rows: [2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', '']],
            pictures: [],
            translations: ['English' => [2 => ['', 'Solid brick.', '', '']]],
        );

        $this->import($workbook);

        $fresh = $listing->fresh();
        $this->assertSame('Ceramic brick M150', $fresh->localizedTitle('en'));
        $this->assertSame('Seramik tuğla M150', $fresh->localizedTitle('tr'));
        $this->assertSame('Solid brick.', $fresh->localizedDescription('en'));
    }

    #[Test]
    public function два_листа_на_одном_языке_отклоняют_книгу(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        $workbook = $this->workbook(
            rows: [2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '', '', '', '']],
            pictures: [],
            translations: [
                'English' => [2 => ['Ceramic brick', '', '', '']],
                'en' => [2 => ['Brick', '', '', '']],
            ],
        );

        $result = $this->import($workbook);

        $this->assertSame(0, $result['created']);
        $this->assertCount(1, $result['errors']);
        $this->assertStringContainsString('одном языке', $result['errors'][0]);
    }

    #[Test]
    public function книга_без_русского_листа_отклоняется(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        $path = tempnam(sys_get_temp_dir(), 'savdex-test').'.xlsx';

        $writer = new Writer;
        $writer->openToFile($path);
        $writer->getCurrentSheet()->setName('English');
        $writer->addRow(Row::fromValues(self::HEADERS));
        $writer->addRow(Row::fromValues(['', 'Ceramic brick', 'ООО «Стройбаза»', '', '', '', '', '']));
        $writer->close();

        $result = $this->import($path);

        $this->assertSame(0, $result['created']);
        $this->assertCount(1, $result['errors']);
        $this->assertStringContainsString('нет русского листа', $result['errors'][0]);
    }

    #[Test]
    public function условия_поставки_и_оплаты_читаются_с_русского_листа(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        $path = tempnam(sys_get_temp_dir(), 'savdex-test').'.xlsx';

        $writer = new Writer;
        $writer->openToFile($path);
        $writer->addRow(Row::fromValues(['Название', 'Компания', 'Условия доставки', 'Оплата']));
        $writer->addRow(Row::fromValues([
            'Кирпич керамический М150', 'ООО «Стройбаза»', 'Самовывоз со склада', 'Предоплата 50 %',
        ]));
        $writer->close();

        $result = $this->import($path);

        $listing = Listing::query()->firstOrFail();

        $this->assertSame([], $result['errors']);
        $this->assertSame('Самовывоз со склада', $listing->delivery_terms);
        $this->assertSame('Предоплата 50 %', $listing->payment_terms);
    }

    #[Test]
    public function незнакомая_валюта_останавливает_строку_с_причиной(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        $workbook = $this->workbook(
            rows: [2 => ['', 'Кирпич керамический М150', 'ООО «Стройбаза»', '', '100', 'XYZ', '', '']],
            pictures: [],
        );

        $result = $this->import($workbook);

        $this->assertSame(0, $result['created']);
        $this->assertCount(1, $result['errors']);
        $this->assertStringContainsString('XYZ', $result['errors'][0]);
    }

    // ── Сборка книги ────────────────────────────────────────────

    /**
     * Книга: русский лист с товарами и, если нужно, языковые листы.
     *
     * Русский лист без языковых остаётся безымянным, как книга из
     * одного листа, сохранённая Excel по умолчанию. С языковыми
     * листами он подписан «Русский» и стоит первым — либо последним,
     * когда проверяется, что лист узнаётся по имени, а не по месту.
     *
     * @param  array<int, list<string>>  $rows  номер строки в Excel → ячейки русского листа
     * @param  array<int, int>  $pictures  номер строки → сколько картинок вставить (на русский лист)
     * @param  array<string, array<int, list<string>>>  $translations  имя вкладки → (номер строки → ячейки)
     */
    private function workbook(array $rows, array $pictures, array $translations = [], bool $russianLast = false): string
    {
        $path = tempnam(sys_get_temp_dir(), 'savdex-test').'.xlsx';

        $writer = new Writer;
        $writer->openToFile($path);

        $first = true;
        $sheet = function (?string $name, array $headers, array $body) use ($writer, &$first): void {
            $page = $first ? $writer->getCurrentSheet() : $writer->addNewSheetAndMakeItCurrent();
            $first = false;

            if ($name !== null) {
                $page->setName($name);
            }

            $writer->addRow(Row::fromValues($headers));

            $last = $body === [] ? 1 : max(array_keys($body));

            for ($number = 2; $number <= $last; $number++) {
                $writer->addRow(Row::fromValues($body[$number] ?? ['']));
            }
        };

        $russian = fn () => $sheet($translations === [] ? null : 'Русский', self::HEADERS, $rows);

        if (! $russianLast) {
            $russian();
        }

        foreach ($translations as $name => $body) {
            $sheet($name, self::TEXT_HEADERS, $body);
        }

        if ($russianLast) {
            $russian();
        }

        $writer->close();

        $this->addPictures($path, $pictures, $russianLast ? count($translations) + 1 : 1);

        return $path;
    }

    /**
     * Дописать в готовую книгу рисунки — так же, как это делает Excel.
     *
     * @param  array<int, int>  $pictures
     * @param  int  $sheet  порядковый номер листа, к которому крепятся рисунки
     */
    private function addPictures(string $path, array $pictures, int $sheet = 1): void
    {
        if ($pictures === []) {
            return;
        }

        $zip = new ZipArchive;
        $zip->open($path);

        $anchors = '';
        $relations = '';
        $number = 0;

        foreach ($pictures as $row => $count) {
            for ($i = 0; $i < $count; $i++) {
                $number++;
                $zip->addFromString("xl/media/image{$number}.png", $this->png($number));

                // Строки и колонки в файле считаются от нуля
                $anchors .= '<xdr:twoCellAnchor editAs="oneCell">'
                    .'<xdr:from><xdr:col>'.(7 + $i).'</xdr:col><xdr:colOff>0</xdr:colOff>'
                    .'<xdr:row>'.($row - 1).'</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>'
                    .'<xdr:to><xdr:col>'.(8 + $i).'</xdr:col><xdr:colOff>0</xdr:colOff>'
                    .'<xdr:row>'.$row.'</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
                    .'<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="'.$number.'" name="Picture '.$number.'"/>'
                    .'<xdr:cNvPicPr/></xdr:nvPicPr>'
                    .'<xdr:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
                    .' r:embed="rId'.$number.'"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
                    .'<xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>'
                    .'</xdr:pic><xdr:clientData/></xdr:twoCellAnchor>';

                $relations .= '<Relationship Id="rId'.$number.'"'
                    .' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"'
                    .' Target="../media/image'.$number.'.png"/>';
            }
        }

        $zip->addFromString('xl/drawings/drawing1.xml',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            .'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"'
            .' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'.$anchors.'</xdr:wsDr>');

        $zip->addFromString('xl/drawings/_rels/drawing1.xml.rels',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            .'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            .$relations.'</Relationships>');

        $zip->addFromString('xl/worksheets/_rels/sheet'.$sheet.'.xml.rels',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            .'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            .'<Relationship Id="rId1"'
            .' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"'
            .' Target="../drawings/drawing1.xml"/></Relationships>');

        $zip->close();
    }

    private function city(string $name): City
    {
        $country = Country::query()->firstOrCreate(['code' => 'uz'], ['sort' => 0, 'is_active' => true]);
        $city = City::query()->create(['country_id' => $country->id, 'slug' => 'tashkent', 'sort' => 0, 'is_active' => true]);
        $city->translations()->create(['locale' => 'ru', 'name' => $name]);

        return $city;
    }

    /** Настоящий PNG: загрузка проверяет файлы через GD. */
    private function png(int $seed): string
    {
        $image = imagecreatetruecolor(40, 30);
        imagefill($image, 0, 0, imagecolorallocate($image, ($seed * 40) % 255, 120, 200));

        ob_start();
        imagepng($image);
        imagedestroy($image);

        return (string) ob_get_clean();
    }

    /** @return array{rows: int, created: int, updated: int, photos: int, errors: list<string>, notes: list<string>} */
    private function import(string $workbook, bool $replace = false): array
    {
        $admin = User::factory()->create(['is_admin' => true, 'admin_role' => User::ADMIN_SUPERADMIN, 'status' => 'active']);

        try {
            return app(ListingWorkbookImport::class)->run($workbook, $admin, $replace);
        } finally {
            File::delete($workbook);
        }
    }
}
