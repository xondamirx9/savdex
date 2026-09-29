<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Exceptions\RecordIsReferenced;
use App\Models\Company;
use App\Models\CompanyType;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Действия админки, которые нельзя проверить правами: они меняют
 * данные, а не только видимость раздела.
 */
class AdminActionsTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    /**
     * Ручное подтверждение почты снимает ограничение на публикацию и
     * раскрытие контактов — то есть открывает деньги. Модератору не даём.
     *
     * Кнопка — в разделе «Пользователи» на Python (python/tests/
     * test_users_editing_admin.py) и видна по праву users.edit; здесь —
     * что у модератора этого права нет.
     */
    #[Test]
    public function модератор_подтвердить_почту_не_может(): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $this->assertFalse(AdminAccess::allows('users.view'));
        $this->assertFalse(AdminAccess::allows('users.edit'));
    }

    /**
     * Тип с компаниями удалять нельзя: у них останется ссылка на
     * несуществующее значение, и в карточке вместо типа появится код.
     *
     * Раздел переехал на Python; запрет теперь в модели, а не в кнопке.
     */
    #[Test]
    public function используемый_тип_компании_не_удаляется(): void
    {
        $type = CompanyType::where('code', 'manufacturer')->firstOrFail();
        Company::factory()->create(['type' => 'manufacturer']);

        try {
            $type->delete();
            $this->fail('тип с компаниями удалился');
        } catch (RecordIsReferenced $e) {
            $this->assertSame(['компании' => 1], $e->references);
        }

        $this->assertModelExists($type);
    }

    /** Ошибочно заведённый тип убирается — иначе мусор в выборе навсегда. */
    #[Test]
    public function неиспользуемый_тип_удаляется(): void
    {
        $type = CompanyType::create(['code' => 'logistics']);

        $type->delete();

        $this->assertModelMissing($type);
    }

    /** Справочник наполнен миграцией: пустой список сломал бы регистрацию. */
    #[Test]
    public function справочник_типов_отдаёт_названия_для_формы(): void
    {
        $options = Company::typeOptions();

        $this->assertArrayHasKey('manufacturer', $options);
        $this->assertSame('Производитель', $options['manufacturer']);
    }

    /** Выключенный тип исчезает из выбора, но остаётся у тех, кто его выбрал. */
    #[Test]
    public function выключенный_тип_не_предлагается_но_подписывается(): void
    {
        CompanyType::where('code', 'service')->update(['is_active' => false]);

        $company = Company::factory()->create(['type' => 'service']);

        $this->assertArrayNotHasKey('service', Company::typeOptions());
        $this->assertSame('service', $company->typeLabel(), 'запасной вариант — сам код, а не пустая строка');
    }
}
