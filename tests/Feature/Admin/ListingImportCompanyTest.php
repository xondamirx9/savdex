<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Listings\Pages\ListListings;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use App\Services\ListingWorkbookImport;
use App\Support\CatalogLookup;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;
use OpenSpout\Common\Entity\Row;
use OpenSpout\Writer\XLSX\Writer;
use PHPUnit\Framework\Attributes\Test;
use RuntimeException;
use Tests\TestCase;

/**
 * Компания в загрузке товаров книгой Excel.
 *
 * Файл на 236 товаров не загрузился ни одной строкой: у части строк
 * столбец «Компания» пуст, а «Sargon Oil, ООО» и «Химкар, ИП» не нашлись —
 * справочник ищет название дословно, а в файле оно записано так, как
 * выгружают реестры: форма после запятой.
 *
 * Отсюда три правила. Название сравнивается без формы и кавычек.
 * Пустой столбец означает компанию, выбранную в окне загрузки.
 * Компании, которой нет, загрузка заводит сама — по галочке.
 */
class ListingImportCompanyTest extends TestCase
{
    use RefreshDatabase;

    private const HEADERS = ['Номер', 'Название', 'Компания', 'Категория', 'Цена', 'Валюта', 'Город', 'Фото'];

    protected function setUp(): void
    {
        parent::setUp();

        Storage::fake('public');
    }

    #[Test]
    public function форма_и_кавычки_в_названии_не_мешают_найти_компанию(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Sargon Oil»']);

        $result = $this->import([
            2 => ['', 'Масло моторное 5W-30', 'Sargon Oil, ООО', '', '', '', '', ''],
            3 => ['', 'Масло трансмиссионное', 'MChJ "Sargon Oil"', '', '', '', '', ''],
        ]);

        $this->assertSame(2, $result['created']);
        $this->assertSame([], $result['errors']);
        $this->assertSame(2, $company->listings()->count());
    }

    /** «Ипотечный центр» начинается на «ип», но формой это не делает. */
    #[Test]
    public function форма_снимается_только_с_краёв_названия(): void
    {
        $this->assertSame('sargon oil', CatalogLookup::companyCore('Sargon Oil, ООО'));
        $this->assertSame('sargon oil', CatalogLookup::companyCore('ООО «Sargon Oil»'));
        $this->assertSame('химкар', CatalogLookup::companyCore('ИП Химкар'));
        $this->assertSame('himkar', CatalogLookup::companyCore('“Himkar” MChJ'));
        $this->assertSame('ипотечный центр', CatalogLookup::companyCore('Ипотечный центр'));
    }

    /**
     * ООО «Химкар» и ИП «Химкар» — два разных продавца. Отдать товар
     * первому попавшемуся — приписать его чужой компании.
     */
    #[Test]
    public function одноимённые_компании_разных_форм_не_угадываются(): void
    {
        Company::factory()->create(['name' => 'ООО «Химкар»']);
        Company::factory()->create(['name' => 'ИП Химкар']);

        $this->assertNull(CatalogLookup::companyId('Химкар'));

        // Точное название по-прежнему находит свою
        $this->assertSame(
            Company::query()->where('name', 'ИП Химкар')->value('id'),
            CatalogLookup::companyId('ИП Химкар'),
        );
    }

    #[Test]
    public function пустой_столбец_берёт_компанию_из_окна_загрузки(): void
    {
        $supplier = Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        // Одноимённый товар другого продавца: цена у него своя,
        // и строка из каталога «Стройбазы» трогать его не должна
        $foreign = Listing::factory()->for(Company::factory()->create())->create([
            'title' => 'Цемент М400', 'price' => 100,
        ]);

        $result = $this->import(
            [2 => ['', 'Цемент М400', '', '', '555', '', '', '']],
            company: $supplier->id,
        );

        $this->assertSame(1, $result['created']);
        $this->assertSame([], $result['errors']);
        $this->assertSame(555.0, (float) $supplier->listings()->where('title', 'Цемент М400')->value('price'));
        $this->assertSame(100.0, (float) $foreign->fresh()->price);
    }

    /** Продавца уже загруженного объявления пустая ячейка не меняет. */
    #[Test]
    public function компания_из_окна_не_переписывает_продавца_существующего(): void
    {
        $owner = Company::factory()->create();
        $listing = Listing::factory()->for($owner)->create(['title' => 'Кирпич М150']);
        $other = Company::factory()->create();

        $result = $this->import(
            [2 => [(string) $listing->id, 'Кирпич М150', '', '', '900', '', '', '']],
            company: $other->id,
        );

        $this->assertSame(1, $result['updated']);
        $this->assertSame($owner->id, $listing->fresh()->company_id);
    }

    #[Test]
    public function без_компании_и_без_выбора_в_окне_строка_объясняет_что_делать(): void
    {
        $result = $this->import([2 => ['', 'Цемент М400', '', '', '', '', '', '']]);

        $this->assertSame(0, $result['created']);
        $this->assertStringContainsString('выберите компанию в окне загрузки', $result['errors'][0]);
    }

    #[Test]
    public function без_галочки_незнакомая_компания_останавливает_строку_с_подсказкой(): void
    {
        $result = $this->import([2 => ['', 'Масло моторное', 'Sargon Oil, ООО', '', '', '', '', '']]);

        $this->assertSame(0, $result['created']);
        $this->assertSame(0, Company::query()->count());
        $this->assertStringContainsString('«Sargon Oil, ООО» не найдена', $result['errors'][0]);
        $this->assertStringContainsString('Заводить компании', $result['errors'][0]);
    }

    #[Test]
    public function с_галочкой_незнакомая_компания_заводится_один_раз(): void
    {
        $result = $this->import([
            2 => ['', 'Масло моторное', 'Sargon Oil, ООО', '', '', '', '', ''],
            3 => ['', 'Антифриз', 'Химкар, ИП', '', '', '', '', ''],
            4 => ['', 'Масло трансмиссионное', 'Sargon Oil, ООО', '', '', '', '', ''],
        ], create: true);

        $this->assertSame(3, $result['created']);
        $this->assertSame(2, $result['companies']);
        $this->assertSame([], $result['errors']);

        $sargon = Company::query()->where('name', 'Sargon Oil, ООО')->sole();

        $this->assertSame(2, $sargon->listings()->count());

        // Как у загрузки справочника: без проверки и с пометкой,
        // что карточку завела площадка
        $this->assertSame(Company::STATUS_ACTIVE, $sargon->status);
        $this->assertSame(Company::VERIFICATION_NONE, $sargon->verification_level);
        $this->assertNotEmpty($sargon->source_note);
        $this->assertNotEmpty($sargon->slug);

        // Каждая заведённая — в отчёте, чтобы опечатку было видно
        $created = array_values(array_filter($result['notes'], fn (string $n): bool => str_contains($n, 'заведена компания')));
        $this->assertCount(2, $created);
        $this->assertStringContainsString('строка 2', mb_strtolower($created[0]));
    }

    #[Test]
    public function с_галочкой_существующая_компания_не_дублируется(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Sargon Oil»']);

        $result = $this->import([2 => ['', 'Масло моторное', 'Sargon Oil, ООО', '', '', '', '', '']], create: true);

        $this->assertSame(0, $result['companies']);
        $this->assertSame(1, Company::query()->count());
        $this->assertSame(1, $company->listings()->count());
    }

    /** Компания по имени «302456789» на витрине хуже остановленной строки. */
    #[Test]
    public function по_одному_инн_компания_не_заводится(): void
    {
        $result = $this->import([2 => ['', 'Масло моторное', '302456789', '', '', '', '', '']], create: true);

        $this->assertSame(0, Company::query()->count());
        $this->assertStringContainsString('впишите название', $result['errors'][0]);
    }

    /** Упала строка — заведённая для неё компания не остаётся пустой карточкой. */
    #[Test]
    public function упавшая_строка_не_оставляет_компанию(): void
    {
        Listing::creating(function (): void {
            throw new RuntimeException('база не приняла объявление');
        });

        $result = $this->import([2 => ['', 'Масло моторное', 'Sargon Oil, ООО', '', '', '', '', '']], create: true);

        $this->assertCount(1, $result['errors']);
        $this->assertSame(0, $result['companies']);
        $this->assertSame(0, Company::query()->count());
    }

    /**
     * Заметка строки — только у неё.
     *
     * Пропущенная ячейка второй строки повторялась у каждой следующей:
     * отчёт о файле на двести товаров рос до десятков тысяч строк.
     */
    #[Test]
    public function заметка_строки_не_переходит_на_следующие(): void
    {
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        $result = $this->import([
            2 => ['', 'Цемент М400', 'ООО «Стройбаза»', 'Нет такой категории', '', '', '', ''],
            3 => ['', 'Щебень', 'ООО «Стройбаза»', '', '', '', '', ''],
            4 => ['', 'Песок', 'ООО «Стройбаза»', '', '', '', '', ''],
        ]);

        $this->assertSame(3, $result['created']);
        $this->assertCount(1, $result['notes']);
        $this->assertStringContainsString('Нет такой категории', $result['notes'][0]);
    }

    #[Test]
    public function окно_загрузки_передаёт_компанию_и_галочку(): void
    {
        $admin = User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);

        $supplier = Company::factory()->create(['name' => 'ООО «Стройбаза»']);

        $workbook = $this->workbook([
            2 => ['', 'Цемент М400', '', '', '', '', '', ''],
            3 => ['', 'Масло моторное', 'Sargon Oil, ООО', '', '', '', '', ''],
        ]);

        Livewire::actingAs($admin)
            ->test(ListListings::class)
            ->callAction(TestAction::make('importWorkbook')->table(), [
                'workbooks' => [
                    UploadedFile::fake()->createWithContent('catalog.xlsx', (string) file_get_contents($workbook)),
                ],
                'company' => $supplier->id,
                'create_companies' => true,
            ])
            ->assertHasNoActionErrors();

        File::delete($workbook);

        $this->assertSame(1, $supplier->listings()->count());
        $this->assertSame(1, Company::query()->where('name', 'Sargon Oil, ООО')->sole()->listings()->count());
    }

    /**
     * @param  array<int, list<string>>  $rows  номер строки в Excel → ячейки
     * @return array{rows: int, created: int, updated: int, photos: int, companies: int, errors: list<string>, notes: list<string>}
     */
    private function import(array $rows, ?int $company = null, bool $create = false): array
    {
        $admin = User::factory()->create(['is_admin' => true, 'admin_role' => User::ADMIN_SUPERADMIN, 'status' => 'active']);
        $workbook = $this->workbook($rows);

        try {
            return app(ListingWorkbookImport::class)->run($workbook, $admin, false, $company, $create);
        } finally {
            File::delete($workbook);
        }
    }

    /** @param array<int, list<string>> $rows */
    private function workbook(array $rows): string
    {
        $path = tempnam(sys_get_temp_dir(), 'savdex-test').'.xlsx';

        $writer = new Writer;
        $writer->openToFile($path);
        $writer->addRow(Row::fromValues(self::HEADERS));

        for ($number = 2; $number <= max(array_keys($rows)); $number++) {
            $writer->addRow(Row::fromValues($rows[$number] ?? ['']));
        }

        $writer->close();

        return $path;
    }
}
