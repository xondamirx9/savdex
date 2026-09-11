<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\DB;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Перенос базы между подключениями.
 *
 * Проверяется на паре SQLite → SQLite: то, что ломалось при разработке,
 * лежит не в диалекте приёмника, а в порядке таблиц — кольцевые связи,
 * дерево категорий, обязательные колонки.
 *
 * Две проверки сюда не попадают: длина строк и разбор JSON. Они читают
 * объявленный тип колонки приёмника, а SQLite сообщает «varchar» без
 * длины и хранит JSON как «text» — на таком приёмнике им просто нечего
 * найти. Работают они только против PostgreSQL, и проверялись на нём.
 */
class CopyDatabaseTest extends TestCase
{
    use RefreshDatabase;

    private string $target;

    protected function setUp(): void
    {
        parent::setUp();

        $this->target = tempnam(sys_get_temp_dir(), 'copy-target-').'.sqlite';
        touch($this->target);

        Config::set('database.connections.copy_target', [
            'driver' => 'sqlite',
            'database' => $this->target,
            'prefix' => '',
            'foreign_key_constraints' => true,
        ]);

        Artisan::call('migrate', ['--database' => 'copy_target', '--force' => true]);
    }

    protected function tearDown(): void
    {
        DB::purge('copy_target');

        if (is_file($this->target)) {
            unlink($this->target);
        }

        parent::tearDown();
    }

    /**
     * Источник — обычная база тестов, приёмник — только что созданный файл.
     *
     * Имя источника берётся у подключения по умолчанию, а не пишется
     * строкой: набор тестов гоняют и на SQLite, и на PostgreSQL, и с
     * зашитым «sqlite» источником на втором оказывалась пустая база —
     * копировать было нечего, а тест об этом молчал.
     */
    private function copy(array $options = []): int
    {
        return Artisan::call('savdex:copy-database', array_merge([
            '--from' => DB::getDefaultConnection(),
            '--to' => 'copy_target',
            '--truncate' => true,
        ], $options));
    }

    #[Test]
    public function переносит_данные_и_сверяет_число_строк(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->for($company)->create();
        Listing::factory()->count(3)->create(['company_id' => $company->id, 'user_id' => $user->id]);

        $this->assertSame(0, $this->copy());

        $this->assertSame(
            DB::connection()->table('listings')->count(),
            DB::connection('copy_target')->table('listings')->count(),
        );

        $this->assertStringContainsString('Число строк совпадает', Artisan::output());
    }

    /**
     * users.company_id → companies и companies.verified_by → users
     * замкнуты в кольцо: одна из колонок вставляется пустой и заполняется
     * вторым проходом. Если он не отработает, связь потеряется молча.
     */
    #[Test]
    public function восстанавливает_кольцевые_связи(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->for($company)->create();
        $company->forceFill(['verified_by' => $user->id])->save();

        $this->assertSame(0, $this->copy());

        $copied = DB::connection('copy_target')->table('companies')->find($company->id);

        $this->assertSame($user->id, (int) $copied->verified_by, 'связь обязана пережить перенос');
        $this->assertSame(
            $company->id,
            (int) DB::connection('copy_target')->table('users')->find($user->id)->company_id,
        );
    }

    /**
     * Дерево категорий вставляется от корней к листьям. Сортировки по
     * parent_id мало: потомок с меньшим id приехал бы раньше родителя.
     */
    #[Test]
    public function сохраняет_дерево_категорий(): void
    {
        $child = Category::factory()->create();
        $parent = Category::factory()->create();
        $child->forceFill(['parent_id' => $parent->id])->save();

        $this->assertGreaterThan($child->id, $parent->id, 'родитель обязан иметь больший id: иначе проверка ничего не значит');

        $this->assertSame(0, $this->copy());

        $copied = DB::connection('copy_target')->table('categories')->find($child->id);

        $this->assertSame($parent->id, (int) $copied->parent_id);
    }

    /**
     * Часть миграций наполняет таблицы сама, поэтому свежий приёмник
     * не пуст. Перенос без очистки обязан отказаться до первой вставки,
     * а не упасть на середине с «duplicate key».
     */
    #[Test]
    public function отказывается_писать_в_непустой_приёмник(): void
    {
        $before = DB::connection('copy_target')->table('company_types')->count();

        $this->assertSame(1, $this->copy(['--truncate' => false]));
        $this->assertStringContainsString('уже есть строки', Artisan::output());

        $this->assertSame(
            $before,
            DB::connection('copy_target')->table('company_types')->count(),
            'приёмник обязан остаться нетронутым',
        );
    }

    #[Test]
    public function отказывается_копировать_подключение_само_в_себя(): void
    {
        $this->assertSame(1, $this->copy(['--to' => DB::getDefaultConnection()]));
        $this->assertStringContainsString('одно подключение', Artisan::output());
    }
}
