<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Imports\CompanyImporter;
use App\Models\Company;
use App\Models\User;
use Filament\Actions\Imports\Models\Import;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Массовая загрузка компаний.
 *
 * Файл готовит заказчик, и язык заголовков заранее не известен:
 * выгрузка из госреестра приходит с одними названиями столбцов,
 * таблица менеджера — с другими.
 */
class CompanyImportTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function синонимы_русских_заголовков_разбираются(): void
    {
        $this->actingAs($this->admin());

        $this->import([
            'ИНН' => '304561278',
            'Компания' => 'ООО «Стройбаза»',
            'Тип' => 'Производитель',
            'Год основания' => '1998',
            'Контактный телефон' => '+998 71 200-00-00',
            'Адрес сайта' => 'stroybaza.uz',
        ], mapped: false);

        $company = Company::query()->firstOrFail();

        $this->assertSame('304561278', $company->tin);
        $this->assertSame('ООО «Стройбаза»', $company->name);
        $this->assertSame('manufacturer', $company->type);
        $this->assertSame(1998, $company->founded_year);
        $this->assertSame('+998 71 200-00-00', $company->phone);
        $this->assertSame('stroybaza.uz', $company->website);
    }

    #[Test]
    public function заголовки_и_тип_компании_на_чужом_языке_разбираются(): void
    {
        $this->actingAs($this->admin());

        $this->import([
            'Tax ID' => '305000111',
            'Company name' => 'Tashkent Matras',
            'Company type' => 'Ishlab chiqaruvchi',
            'Employees' => '50-100',
            'Web site' => 'matras.uz',
            'Kuruluş yılı' => '2005',
        ], mapped: false);

        $company = Company::query()->firstOrFail();

        $this->assertSame('305000111', $company->tin);
        $this->assertSame('Tashkent Matras', $company->name);
        $this->assertSame('manufacturer', $company->type);
        $this->assertSame('50-100', $company->employees_range);
        $this->assertSame('matras.uz', $company->website);
        $this->assertSame(2005, $company->founded_year);
    }

    #[Test]
    public function тип_вне_справочника_сохраняется_как_есть(): void
    {
        $this->actingAs($this->admin());

        $this->import(['ИНН' => '300111222', 'Название' => 'Быстрая логистика', 'Тип компании' => 'Логистика']);

        $this->assertSame('логистика', Company::query()->firstOrFail()->type);
    }

    private function admin(): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);
    }

    /**
     * Прогнать одну строку через импортёр так, как это делает
     * очередь Filament.
     *
     * @param  array<string, string>  $row
     * @param  bool  $mapped  соответствие из окна импорта; false — то,
     *                        что Filament не угадал ни одного столбца
     */
    private function import(array $row, bool $mapped = true): void
    {
        $import = Import::create([
            'user_id' => auth()->id(),
            'file_name' => 'companies.csv',
            'file_path' => 'companies.csv',
            'importer' => CompanyImporter::class,
            'total_rows' => 1,
        ]);

        $columnMap = [];

        if ($mapped) {
            foreach (CompanyImporter::getColumns() as $column) {
                $columnMap[$column->getName()] = $column->getExampleHeader();
            }
        }

        (new CompanyImporter($import, $columnMap, []))($row);
    }
}
