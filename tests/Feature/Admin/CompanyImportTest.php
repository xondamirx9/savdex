<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Imports\CompanyImporter;
use App\Models\Company;
use App\Models\Country;
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
 *
 * Ячейки в таком файле набраны руками: прочерк вместо пустоты, две
 * почты через косую черту, «около 6500 (по публичным данным)»
 * в численности. Раньше на каждой такой строке импорт спотыкался
 * и терял компанию целиком — проверка ниже держит это.
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

    /**
     * Прочерк — это «данных нет», а не значение.
     *
     * До этого «—» в ИНН делал всех иностранных поставщиков одной
     * компанией: firstOrNew находил первую же строку с таким «ИНН»
     * и переписывал её следующей.
     */
    #[Test]
    public function прочерк_вместо_значения_не_ломает_строку(): void
    {
        $this->actingAs($this->admin());

        $this->import(['ИНН' => '—', 'Название' => 'Awal Dairy', 'Почта' => '—', 'Год основания' => '—', 'Телефон' => '-']);
        $this->import(['ИНН' => '—', 'Название' => 'Alba', 'Почта' => 'н/д', 'Сотрудников' => 'не указано']);

        $this->assertSame(2, Company::count());

        $company = Company::where('name', 'Awal Dairy')->firstOrFail();

        $this->assertNull($company->tin);
        $this->assertNull($company->email);
        $this->assertNull($company->founded_year);
        $this->assertNull($company->phone);
        $this->assertNull(Company::where('name', 'Alba')->firstOrFail()->employees_range);
    }

    /** Несколько значений в ячейке: берём первое, строку не теряем. */
    #[Test]
    public function несколько_значений_в_ячейке_берут_первое(): void
    {
        $this->actingAs($this->admin());

        $this->import([
            'Название' => 'Arabian Pipes',
            'Почта' => 'info@arabian-pipes.com / export_sales@arabian-pipes.com',
            'Телефон' => '+966 11 8133333 / +966 12 6104000 / +966 13 8495000',
            'Год основания' => '1827 / 2003',
            'Сайт' => 'https://arabian-pipes.com / https://shop.arabian-pipes.com',
        ]);

        $company = Company::query()->firstOrFail();

        $this->assertSame('info@arabian-pipes.com', $company->email);
        $this->assertSame('+966 11 8133333', $company->phone);
        $this->assertSame(1827, $company->founded_year);
        $this->assertSame('https://arabian-pipes.com', $company->website);
    }

    /**
     * Прядильные и стекольные заводы Европы старше 1850 года,
     * и отказывать им в загрузке из-за нижней границы незачем.
     */
    #[Test]
    public function старая_компания_и_численность_словами(): void
    {
        $this->actingAs($this->admin());

        $this->import([
            'Название' => 'Villeroy & Boch',
            'Год основания' => '1790',
            'Сотрудников' => 'около 6500 (по публичным данным)',
        ]);

        $company = Company::query()->firstOrFail();

        $this->assertSame(1790, $company->founded_year);
        $this->assertSame('6500', $company->employees_range);
    }

    /** Тип узнаётся по корню слова, а не по точному совпадению. */
    #[Test]
    public function тип_узнаётся_по_корню_слова(): void
    {
        $this->actingAs($this->admin());

        $this->import(['Название' => 'Hateks', 'Тип компании' => 'производство, экспорт, торговля']);
        $this->import(['Название' => 'ITWorx', 'Тип компании' => 'IT']);
        $this->import(['Название' => 'Ekol', 'Тип компании' => 'Üretim ve ihracat']);

        $this->assertSame('manufacturer', Company::where('name', 'Hateks')->value('type'));
        $this->assertSame('service', Company::where('name', 'ITWorx')->value('type'));
        $this->assertSame('manufacturer', Company::where('name', 'Ekol')->value('type'));
    }

    /** Страна из таблицы — по названию на любом языке. */
    #[Test]
    public function страна_из_таблицы_проставляется(): void
    {
        $this->actingAs($this->admin());

        $poland = Country::create(['code' => 'pl', 'phone_code' => '+48', 'currency_code' => 'PLN', 'is_active' => true]);
        $poland->translations()->create(['locale' => 'ru', 'name' => 'Польша']);

        $this->import(['Название' => 'Forte', 'Страна' => 'Польша']);
        $this->import(['Название' => 'Szynaka', 'Страна' => 'Мордор']);

        $this->assertSame($poland->id, Company::where('name', 'Forte')->value('country_id'));
        $this->assertNull(Company::where('name', 'Szynaka')->value('country_id'));
    }

    /**
     * Повторная загрузка того же файла обновляет, а не удваивает.
     *
     * Иностранные поставщики приходят без ИНН пачками, и второй заход
     * с исправленным файлом иначе оставлял бы в базе две карточки
     * на одну компанию.
     */
    #[Test]
    public function повторная_загрузка_без_инн_не_плодит_дублей(): void
    {
        $this->actingAs($this->admin());

        $this->import(['Название' => 'Comforty', 'Почта' => 'comforty@comforty.pl']);
        $this->import(['Название' => 'Comforty', 'Почта' => 'info@comforty.pl', 'Год основания' => '1995']);

        $this->assertSame(1, Company::count());

        $company = Company::query()->firstOrFail();

        $this->assertSame('info@comforty.pl', $company->email);
        $this->assertSame(1995, $company->founded_year);
    }

    /** Компанию с ИНН строка без ИНН не подменяет, даже при том же названии. */
    #[Test]
    public function компанию_с_инн_безымянная_строка_не_трогает(): void
    {
        $this->actingAs($this->admin());

        $this->import(['ИНН' => '304561278', 'Название' => 'Стройбаза', 'Почта' => 'info@stroybaza.uz']);
        $this->import(['ИНН' => '—', 'Название' => 'Стройбаза', 'Почта' => 'other@example.com']);

        $this->assertSame(2, Company::count());
        $this->assertSame('info@stroybaza.uz', Company::where('tin', '304561278')->value('email'));
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
