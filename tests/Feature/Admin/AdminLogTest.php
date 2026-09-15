<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\AdminActions\AdminActionResource;
use App\Models\AdminAction;
use App\Models\Company;
use App\Models\User;
use App\Support\AdminAccess;
use App\Support\AdminLog;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use RuntimeException;
use Tests\TestCase;

/**
 * Журнал действий администраторов.
 *
 * Проверяется не то, что записи появляются, а то, ради чего журнал
 * заводят: что он полон, что его нельзя подчистить и что в него не
 * утекает лишнее.
 */
class AdminLogTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role = AdminAccess::SUPERADMIN): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    // ── Что попадает в журнал ───────────────────────────────────────

    #[Test]
    public function правка_администратора_попадает_в_журнал(): void
    {
        $this->actingAs($this->admin());

        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $company->forceFill(['name' => 'ООО «Стройбаза плюс»'])->save();

        $entry = AdminAction::where('action', 'updated')->sole();

        $this->assertSame('companies', $entry->section);
        $this->assertSame('ООО «Стройбаза плюс»', $entry->subject_label);
        $this->assertSame('ООО «Стройбаза»', $entry->changes['before']['name']);
        $this->assertSame('ООО «Стройбаза плюс»', $entry->changes['after']['name']);
    }

    /**
     * Правка владельца компании в кабинете — не действие администратора.
     *
     * Журнал ведётся ради проверки сотрудников. Записи о том, что клиент
     * поправил себе телефон, в нём только мешают искать.
     */
    #[Test]
    public function правка_обычного_пользователя_в_журнал_не_идёт(): void
    {
        $this->actingAs(User::factory()->create(['is_admin' => false]));

        Company::factory()->create()->forceFill(['name' => 'Другое имя'])->save();

        $this->assertSame(0, AdminAction::count());
    }

    /** Без вошедшего пользователя — сидеры, консоль, очереди — журнал молчит. */
    #[Test]
    public function фоновая_правка_в_журнал_не_идёт(): void
    {
        Company::factory()->create()->forceFill(['name' => 'Из консоли'])->save();

        $this->assertSame(0, AdminAction::count());
    }

    /**
     * Блокировка называется блокировкой.
     *
     * Технически это правка одного поля, но ищут её фильтром по
     * действию, а не чтением истории изменений подряд.
     */
    #[Test]
    public function блокировка_записывается_своим_именем(): void
    {
        $this->actingAs($this->admin());

        $company = Company::factory()->create(['status' => 'active']);
        $company->forceFill(['status' => 'blocked'])->save();

        $this->assertTrue(AdminAction::where('action', 'blocked')->exists());

        $company->forceFill(['status' => 'active'])->save();

        $this->assertTrue(AdminAction::where('action', 'unblocked')->exists());
    }

    #[Test]
    public function создание_и_удаление_записываются(): void
    {
        $this->actingAs($this->admin());

        $company = Company::factory()->create();
        $company->delete();

        $this->assertTrue(AdminAction::where('action', 'created')->exists());
        $this->assertTrue(AdminAction::where('action', 'deleted')->exists());
    }

    /** Кто, когда и в какой роль был — снимком, а не ссылкой. */
    #[Test]
    public function автор_сохраняется_снимком(): void
    {
        $actor = $this->admin(AdminAccess::MODERATOR);
        $actor->forceFill(['name' => 'Пётр Модераторов'])->save();

        $this->actingAs($actor);

        Company::factory()->create();

        $entry = AdminAction::where('action', 'created')->sole();

        $this->assertSame('Пётр Модераторов', $entry->user_name);
        $this->assertSame(AdminAccess::MODERATOR, $entry->user_role);
        $this->assertSame($actor->id, $entry->user_id);
    }

    /**
     * Имя автора переживает удаление учётной записи.
     *
     * Вопрос «кто это сделал» задают как раз после увольнения, и ответ
     * «пользователь #17, которого больше нет» на него не отвечает.
     */
    #[Test]
    public function запись_переживает_удаление_автора(): void
    {
        $actor = $this->admin();
        $actor->forceFill(['name' => 'Уволенный Сотрудник'])->save();

        $this->actingAs($actor);
        Company::factory()->create();

        $actor->forceDelete();

        $entry = AdminAction::where('action', 'created')->sole();

        $this->assertSame('Уволенный Сотрудник', $entry->user_name);
        $this->assertNull($entry->fresh()->user_id, 'ссылка обнуляется, снимок остаётся');
    }

    // ── Чего в журнале быть не должно ───────────────────────────────

    /** Пароль в истории изменений — это пароль, лежащий открыто навсегда. */
    #[Test]
    public function пароль_в_журнал_не_попадает(): void
    {
        $this->actingAs($this->admin());

        $victim = User::factory()->create();
        $victim->forceFill(['password' => 'ОченьДлинныйПароль123'])->save();

        $entry = AdminAction::where('section', 'users')->where('action', 'updated')->sole();

        $this->assertSame('···', $entry->changes['after']['password']);
        $this->assertStringNotContainsString('ОченьДлинныйПароль', json_encode($entry->changes) ?: '');
    }

    #[Test]
    public function длинные_значения_обрезаются(): void
    {
        $this->actingAs($this->admin());

        $company = Company::factory()->create();
        $company->forceFill(['description' => str_repeat('а', 5000)])->save();

        $entry = AdminAction::where('action', 'updated')->sole();

        $this->assertLessThanOrEqual(301, mb_strlen($entry->changes['after']['description']));
    }

    // ── Журнал нельзя подчистить ────────────────────────────────────

    #[Test]
    public function запись_журнала_нельзя_изменить(): void
    {
        $this->actingAs($this->admin());
        Company::factory()->create();

        $entry = AdminAction::sole();

        $this->expectException(RuntimeException::class);

        // Значение заведомо другое: правка «на то же самое» модель не
        // сохраняет вовсе, и запрет до неё просто не доходит
        $entry->forceFill(['action' => 'deleted'])->save();
    }

    #[Test]
    public function запись_журнала_нельзя_удалить(): void
    {
        $this->actingAs($this->admin());
        Company::factory()->create();

        $this->expectException(RuntimeException::class);

        AdminAction::sole()->delete();
    }

    /** Ни у кого, включая суперадмина: в панели этих кнопок нет вовсе. */
    #[Test]
    public function в_панели_журнал_только_на_чтение(): void
    {
        $this->actingAs($this->admin());
        Company::factory()->create();

        $entry = AdminAction::sole();

        $this->assertTrue(AdminActionResource::canViewAny());
        $this->assertFalse(AdminActionResource::canCreate());
        $this->assertFalse(AdminActionResource::canEdit($entry));
        $this->assertFalse(AdminActionResource::canDelete($entry));
        $this->assertFalse(AdminActionResource::canForceDelete($entry));
    }

    // ── Кто видит журнал ────────────────────────────────────────────

    #[Test]
    public function журнал_видят_только_суперадмин_админ_и_финансы(): void
    {
        foreach (AdminAccess::ROLES as $role => $label) {
            $this->actingAs(User::factory()->create([
                'is_admin' => true, 'admin_role' => $role, 'status' => 'active',
            ]));

            $expected = in_array($role, [
                AdminAccess::SUPERADMIN, AdminAccess::ADMIN, AdminAccess::FINANCE,
            ], true);

            $this->assertSame($expected, AdminActionResource::canViewAny(), $label);
        }
    }

    // ── Записи по существу ──────────────────────────────────────────

    /** Выгрузка — не правка записи, но след оставить обязана. */
    #[Test]
    public function выгрузка_записывается_без_записи(): void
    {
        $actor = $this->admin();

        AdminLog::record('exported', 'companies', actor: $actor);

        $entry = AdminAction::where('action', 'exported')->sole();

        $this->assertSame('companies', $entry->section);
        $this->assertNull($entry->subject_id);
    }

    /** Сбой журнала не должен ронять действие, которое он записывает. */
    #[Test]
    public function сбой_записи_не_роняет_действие(): void
    {
        $this->actingAs($this->admin());

        AdminLog::record('created', str_repeat('раздел', 50), note: 'слишком длинный раздел');

        $this->assertTrue(true, 'исключение не вышло наружу');
    }
}
