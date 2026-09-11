<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\File;
use OpenSpout\Reader\XLSX\Reader;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Выгрузка базы в две книги Excel.
 *
 * Выгрузка делается перед очисткой базы, то есть ровно тогда, когда
 * проверить её по оригиналу уже нельзя. Поэтому проверяется не только
 * то, что файл создан, но и что в нём именно те строки и значения.
 */
class ExportWorkbooksTest extends TestCase
{
    use RefreshDatabase;

    private string $dir;

    protected function setUp(): void
    {
        parent::setUp();

        $this->dir = storage_path('framework/testing/export-'.bin2hex(random_bytes(4)));
    }

    protected function tearDown(): void
    {
        File::deleteDirectory($this->dir);

        parent::tearDown();
    }

    private function export(): int
    {
        return Artisan::call('savdex:export-xlsx', ['--dir' => $this->dir]);
    }

    /** @return array<string, list<list<mixed>>> */
    private function sheets(string $prefix): array
    {
        $files = glob($this->dir."/savdex-{$prefix}-*.xlsx");

        $this->assertNotEmpty($files, "файл {$prefix} не создан");

        $reader = new Reader;
        $reader->open($files[0]);

        $sheets = [];

        foreach ($reader->getSheetIterator() as $sheet) {
            $rows = [];

            foreach ($sheet->getRowIterator() as $row) {
                $rows[] = $row->toArray();
            }

            $sheets[$sheet->getName()] = $rows;
        }

        $reader->close();

        return $sheets;
    }

    /** @param list<list<mixed>> $rows */
    private function cell(array $rows, string $header, int $row): mixed
    {
        $column = array_search($header, $rows[0], true);

        $this->assertNotFalse($column, "колонки «{$header}» нет в листе");

        return $rows[$row][$column] ?? null;
    }

    #[Test]
    public function создаёт_две_книги_и_сверка_проходит(): void
    {
        Company::factory()->count(2)->create();

        $this->assertSame(0, $this->export());
        $this->assertStringContainsString('Все листы сошлись', Artisan::output());

        $this->assertCount(1, glob($this->dir.'/savdex-companies-*.xlsx'));
        $this->assertCount(1, glob($this->dir.'/savdex-listings-*.xlsx'));
    }

    /** Первый лист объясняет, что лежит на остальных. */
    #[Test]
    public function первым_листом_идёт_справка(): void
    {
        Company::factory()->create();

        $this->assertSame(0, $this->export());

        $sheets = $this->sheets('companies');

        $this->assertSame('Справка', array_key_first($sheets));
        $this->assertContains('Компании', array_keys($sheets));
        $this->assertContains('Сотрудники', array_keys($sheets));
    }

    #[Test]
    public function значения_компании_попадают_в_файл(): void
    {
        $company = Company::factory()->create([
            'name' => 'ООО «Пробный поставщик»',
            'tin' => '00123456789',
            'phone' => '+998901234567',
        ]);

        $this->assertSame(0, $this->export());

        $rows = $this->sheets('companies')['Компании'];

        $this->assertSame($company->id, $this->cell($rows, 'ID', 1));
        $this->assertSame('ООО «Пробный поставщик»', $this->cell($rows, 'Название', 1));
    }

    /**
     * Excel охотно превращает «00123…» в число и съедает ведущие нули.
     * Для ИНН и телефона это порча данных, а выгрузка делается как раз
     * затем, чтобы ничего не потерять.
     */
    #[Test]
    public function инн_и_телефон_остаются_текстом(): void
    {
        Company::factory()->create([
            'tin' => '00123456789',
            'phone' => '+998901234567',
        ]);

        $this->assertSame(0, $this->export());

        $rows = $this->sheets('companies')['Компании'];

        $this->assertSame('00123456789', $this->cell($rows, 'ИНН / СТИР', 1));
        $this->assertSame('+998901234567', $this->cell($rows, 'Телефон', 1));
    }

    /**
     * Мягко удалённые записи — первое, что теряется при выгрузке через
     * модели: Eloquent прячет их глобальной областью видимости.
     */
    #[Test]
    public function удалённые_записи_не_пропадают(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->for($company)->create();
        $listing = Listing::factory()->create(['company_id' => $company->id, 'user_id' => $user->id]);

        $listing->delete();

        $this->assertSame(0, $this->export());

        $rows = $this->sheets('listings')['Объявления'];

        $this->assertCount(2, $rows, 'шапка и одна строка');
        $this->assertSame($listing->id, $this->cell($rows, 'ID', 1));
        $this->assertNotSame('', $this->cell($rows, 'Удалено', 1), 'дата удаления обязана быть в файле');
    }

    /** Читаемое название стоит рядом с идентификатором, а не вместо него. */
    #[Test]
    public function рядом_с_идентификатором_стоит_название(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Ромашка»']);
        $user = User::factory()->for($company)->create();
        Listing::factory()->create(['company_id' => $company->id, 'user_id' => $user->id]);

        $this->assertSame(0, $this->export());

        $rows = $this->sheets('listings')['Объявления'];

        $this->assertSame($company->id, $this->cell($rows, 'ID компании', 1));
        $this->assertSame('ООО «Ромашка»', $this->cell($rows, 'Компания', 1));
    }

    /**
     * Счётчики — то, по чему отличают живую компанию от тестовой, и
     * пустая ячейка вместо нуля сбивает это решение.
     */
    #[Test]
    public function считает_объявления_и_сотрудников_компании(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->for($company)->create();

        Listing::factory()->count(2)->create([
            'company_id' => $company->id,
            'user_id' => $user->id,
            'status' => Listing::STATUS_ACTIVE,
        ]);

        Listing::factory()->create([
            'company_id' => $company->id,
            'user_id' => $user->id,
            'status' => Listing::STATUS_DRAFT,
        ]);

        $пустая = Company::factory()->create();

        $this->assertSame(0, $this->export());

        $rows = $this->sheets('companies')['Компании'];

        $строка = $company->id < $пустая->id ? 1 : 2;
        $пустаяСтрока = $строка === 1 ? 2 : 1;

        $this->assertSame(1, $this->cell($rows, 'Учётных записей', $строка));
        $this->assertSame(3, $this->cell($rows, 'Объявлений всего', $строка));
        $this->assertSame(2, $this->cell($rows, 'Из них активных', $строка));
        $this->assertSame(0, $this->cell($rows, 'Объявлений всего', $пустаяСтрока), 'ноль, а не пустая ячейка');
    }

    /** Пустая база — это пустые листы, а не отказ. */
    #[Test]
    public function работает_на_пустой_базе(): void
    {
        $this->assertSame(0, $this->export());

        $rows = $this->sheets('companies')['Компании'];

        $this->assertCount(1, $rows, 'только шапка');
    }
}
