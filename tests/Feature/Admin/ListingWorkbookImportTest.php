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
 */
class ListingWorkbookImportTest extends TestCase
{
    use RefreshDatabase;

    private const HEADERS = ['Номер', 'Название', 'Компания', 'Категория', 'Цена', 'Валюта', 'Город', 'Фото'];

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
        $this->assertSame(Listing::STATUS_ACTIVE, $listing->status);
        $this->assertNotNull($listing->slug);
        $this->assertSame(1, $listing->images()->count());
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
                'workbook' => UploadedFile::fake()->createWithContent('catalog.xlsx', (string) file_get_contents($workbook)),
            ])
            ->assertHasNoActionErrors();

        $this->assertSame(1, $listing->images()->count());
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
        $this->assertSame(1, $result['created']);
        $this->assertSame('Кирпич и блоки', $listing->category?->name());
        $this->assertSame('Ташкент', $listing->city?->name());
        $this->assertSame('UZS', $listing->currency);
        $this->assertSame(1_200.0, (float) $listing->price);
        $this->assertSame(Listing::STATUS_ACTIVE, $listing->status);
    }

    #[Test]
    public function книга_на_пяти_языках_читается_целиком(): void
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
        $this->assertSame(Listing::STATUS_ACTIVE, $listing->status);
    }

    // ── Сборка книги ────────────────────────────────────────────

    /**
     * @param  array<int, list<string>>  $rows  номер строки в Excel → ячейки
     * @param  array<int, int>  $pictures  номер строки → сколько картинок вставить
     */
    private function workbook(array $rows, array $pictures): string
    {
        $path = tempnam(sys_get_temp_dir(), 'savdex-test').'.xlsx';

        $writer = new Writer;
        $writer->openToFile($path);
        $writer->addRow(Row::fromValues(self::HEADERS));

        $last = $rows === [] ? 1 : max(array_keys($rows));

        for ($number = 2; $number <= $last; $number++) {
            $writer->addRow(Row::fromValues($rows[$number] ?? ['']));
        }

        $writer->close();

        $this->addPictures($path, $pictures);

        return $path;
    }

    /**
     * Дописать в готовую книгу рисунки — так же, как это делает Excel.
     *
     * @param  array<int, int>  $pictures
     */
    private function addPictures(string $path, array $pictures): void
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

        $zip->addFromString('xl/worksheets/_rels/sheet1.xml.rels',
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

    /** @return array{rows: int, created: int, updated: int, photos: int, errors: list<string>} */
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
