<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Pages\Complaints;
use App\Filament\Pages\Invoices;
use App\Filament\Resources\Broadcasts\BroadcastResource;
use App\Filament\Resources\Categories\CategoryResource;
use App\Filament\Resources\Companies\CompanyResource;
use App\Filament\Resources\CompanyDocuments\CompanyDocumentResource;
use App\Filament\Resources\CompanyTypes\CompanyTypeResource;
use App\Filament\Resources\CreditPacks\CreditPackResource;
use App\Filament\Resources\ItTasks\ItTaskResource;
use App\Filament\Resources\LandingBlocks\LandingBlockResource;
use App\Filament\Resources\Listings\ListingResource;
use App\Filament\Resources\NewsPosts\NewsPostResource;
use App\Filament\Resources\Pages\PageResource;
use App\Filament\Resources\Plans\PlanResource;
use App\Filament\Resources\PromoCodes\PromoCodeResource;
use App\Filament\Resources\Resumes\ResumeResource;
use App\Filament\Resources\Reviews\ReviewResource;
use App\Filament\Resources\Settings\SettingResource;
use App\Filament\Resources\Subscriptions\SubscriptionResource;
use App\Filament\Resources\Tenders\TenderResource;
use App\Filament\Resources\Users\UserResource;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Facades\Filament;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Девять ролей в админке (docs/admin-roles.md).
 *
 * Проверяется не видимость пунктов меню, а право открыть раздел:
 * скрытая ссылка ничего не защищает — адрес вводится руками.
 *
 * Ожидания записаны здесь списком, а не выведены из AdminAccess:
 * тест, который спрашивает матрицу, что она разрешает, и сверяет
 * ответ с ней же, не проверяет ничего. Список приходится править
 * руками при каждом изменении прав — это и есть его работа.
 */
class AdminAccessTest extends TestCase
{
    use RefreshDatabase;

    /** Все разделы панели, у которых есть экран. */
    private const ALL = [
        UserResource::class,
        CompanyResource::class,
        ListingResource::class,
        TenderResource::class,
        ItTaskResource::class,
        CompanyDocumentResource::class,
        ResumeResource::class,
        ReviewResource::class,
        Complaints::class,
        Invoices::class,
        SubscriptionResource::class,
        PlanResource::class,
        PromoCodeResource::class,
        CreditPackResource::class,
        CategoryResource::class,
        CompanyTypeResource::class,
        PageResource::class,
        NewsPostResource::class,
        LandingBlockResource::class,
        BroadcastResource::class,
        SettingResource::class,
    ];

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    /**
     * Что каждая роль видит. Всё, чего нет в списке, видеть не должна.
     *
     * @return array<string, array{string, list<class-string>}>
     */
    public static function разделыРолей(): array
    {
        return [
            'суперадмин' => [AdminAccess::SUPERADMIN, self::ALL],

            'администратор' => [AdminAccess::ADMIN, [
                UserResource::class, CompanyResource::class, ListingResource::class,
                TenderResource::class, ItTaskResource::class, CompanyDocumentResource::class,
                ResumeResource::class, ReviewResource::class, Complaints::class,
                CategoryResource::class, CompanyTypeResource::class,
                PageResource::class, NewsPostResource::class, LandingBlockResource::class,
                BroadcastResource::class,
            ]],

            'продажи' => [AdminAccess::SALES, [
                CompanyResource::class, ListingResource::class,
                TenderResource::class, PromoCodeResource::class,
            ]],

            'менеджер поставщиков' => [AdminAccess::SUPPLIER_MANAGER, [
                CompanyResource::class, ListingResource::class,
                TenderResource::class, CompanyDocumentResource::class,
            ]],

            'менеджер покупателей' => [AdminAccess::BUYER_MANAGER, [
                CompanyResource::class, ListingResource::class,
                TenderResource::class, CompanyDocumentResource::class,
            ]],

            'модератор' => [AdminAccess::MODERATOR, [
                CompanyResource::class, ListingResource::class, TenderResource::class,
                ItTaskResource::class, CompanyDocumentResource::class,
                ResumeResource::class, ReviewResource::class, Complaints::class,
                CategoryResource::class, CompanyTypeResource::class,
            ]],

            'финансы' => [AdminAccess::FINANCE, [
                CompanyResource::class, Invoices::class, SubscriptionResource::class,
                PlanResource::class, PromoCodeResource::class, CreditPackResource::class,
            ]],

            'поддержка' => [AdminAccess::SUPPORT, [
                UserResource::class, CompanyResource::class, ListingResource::class,
                ItTaskResource::class, ResumeResource::class, ReviewResource::class, Complaints::class,
                SubscriptionResource::class,
            ]],

            'контент' => [AdminAccess::CONTENT_MANAGER, [
                CategoryResource::class, CompanyTypeResource::class,
                PageResource::class, NewsPostResource::class, LandingBlockResource::class,
                BroadcastResource::class,
            ]],
        ];
    }

    /**
     * @param  list<class-string>  $visible
     */
    #[Test]
    #[DataProvider('разделыРолей')]
    public function роль_видит_ровно_свои_разделы(string $role, array $visible): void
    {
        $this->actingAs($this->admin($role));

        foreach (self::ALL as $section) {
            $expected = in_array($section, $visible, true);

            $this->assertSame(
                $expected,
                $section::canAccess(),
                $expected
                    ? "роль «{$role}» должна видеть {$section}"
                    : "роль «{$role}» не должна видеть {$section}",
            );
        }
    }

    // ── Вход в панель ───────────────────────────────────────────────

    #[Test]
    public function обычный_пользователь_в_панель_не_попадает(): void
    {
        $user = User::factory()->create(['is_admin' => false]);

        $this->assertFalse($user->canAccessPanel(Filament::getPanel('admin')));
    }

    /** Заблокированный администратор — тоже не администратор. */
    #[Test]
    public function заблокированный_админ_в_панель_не_попадает(): void
    {
        $user = $this->admin(AdminAccess::SUPERADMIN);
        $user->forceFill(['status' => 'blocked'])->save();

        $this->assertFalse($user->fresh()->canAccessPanel(Filament::getPanel('admin')));
    }

    /**
     * Блокировка отбирает права немедленно, не дожидаясь выхода.
     *
     * Проверка входа в панель закрывает только следующий вход. Права
     * отбирает эта, и потому она проверяется отдельно: сотрудник,
     * заблокированный посреди работы, не должен успеть нажать кнопку.
     */
    #[Test]
    public function заблокированный_админ_теряет_все_права(): void
    {
        $user = $this->admin(AdminAccess::SUPERADMIN);
        $user->forceFill(['status' => 'blocked'])->save();

        $this->assertFalse($user->fresh()->hasAdminAbility('companies.view'));
    }

    /**
     * Роль не назначена — прав нет.
     *
     * Раньше такой администратор молча считался модератором. Пустая
     * панель заставит прийти и спросить; чужие права по умолчанию —
     * нет, и это разница между «неудобно» и «опасно».
     */
    #[Test]
    public function админ_без_роли_не_получает_прав(): void
    {
        $user = $this->admin(AdminAccess::MODERATOR);
        $user->forceFill(['admin_role' => null])->save();

        $this->assertSame([], $user->fresh()->adminAbilities());
        $this->assertSame('Роль не назначена', $user->fresh()->adminRoleLabel());
    }

    // ── Границы ролей ───────────────────────────────────────────────

    /** Администратор не видит денег — ни сумм, ни отчётов. */
    #[Test]
    public function администратор_не_открывает_счета(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $this->assertFalse(Invoices::canAccess());
        $this->assertFalse(AdminAccess::allows('payments.view'));
    }

    /**
     * Администратор не раздаёт роли.
     *
     * Иначе граница между администратором и суперадмином существует
     * ровно до первой попытки её обойти.
     */
    #[Test]
    public function администратор_не_раздаёт_роли(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $this->assertFalse(AdminAccess::allows('roles.edit'));
    }

    /** Модератор модерирует, но не удаляет: удаление уносит оплаченное. */
    #[Test]
    public function модератор_модерирует_но_не_удаляет(): void
    {
        $this->actingAs($this->admin(AdminAccess::MODERATOR));

        $this->assertTrue(AdminAccess::allows('listings.moderate'));
        $this->assertFalse(AdminAccess::allows('listings.delete'));
        $this->assertFalse(AdminAccess::allows('companies.delete'));
    }

    /** Финансы проверяют оплаты, но цену тарифа не меняют. */
    #[Test]
    public function финансы_не_меняют_тарифы(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        $this->assertTrue(AdminAccess::allows('plans.view'));
        $this->assertFalse(AdminAccess::allows('plans.edit'));
        $this->assertTrue(AdminAccess::allows('payments.edit'));
    }

    /** Поддержка смотрит и отвечает, но данные пользователя не правит. */
    #[Test]
    public function поддержка_не_правит_пользователей(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPPORT));

        $this->assertTrue(AdminAccess::allows('users.view'));
        $this->assertFalse(AdminAccess::allows('users.edit'));
        $this->assertFalse(AdminAccess::allows('payments.view'));
    }

    /** Продажи выдают промокоды сами — решение заказчика. */
    #[Test]
    public function продажи_заводят_промокоды(): void
    {
        $this->actingAs($this->admin(AdminAccess::SALES));

        $this->assertTrue(AdminAccess::allows('promocodes.create'));
        $this->assertFalse(AdminAccess::allows('promocodes.delete'));
    }

    /** Менеджеры видят, что завезли, но решение по этому принимает модератор. */
    #[Test]
    public function менеджеры_видят_свои_документы_но_не_модерируют(): void
    {
        foreach ([AdminAccess::SUPPLIER_MANAGER, AdminAccess::BUYER_MANAGER] as $role) {
            $this->actingAs($this->admin($role));

            $this->assertTrue(AdminAccess::allows('documents.view'), "{$role} должен видеть документы");
            $this->assertFalse(AdminAccess::allows('documents.moderate'), "{$role} не должен модерировать");
        }
    }

    // ── Выгрузка и загрузка ─────────────────────────────────────────

    /**
     * Выгрузка не достаётся вместе с правом на правку.
     *
     * Посмотреть список на экране и унести его файлом — разные по
     * последствиям действия: файл уходит с площадки целиком.
     */
    #[Test]
    public function правка_не_даёт_выгрузки(): void
    {
        $this->actingAs($this->admin(AdminAccess::MODERATOR));

        $this->assertTrue(AdminAccess::allows('companies.edit'));
        $this->assertFalse(AdminAccess::allows('companies.export'));
    }

    #[Test]
    public function администратор_выгружает_и_загружает_компании(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $this->assertTrue(AdminAccess::allows('companies.export'));
        $this->assertTrue(AdminAccess::allows('companies.import'));
    }

    // ── Область видимости ───────────────────────────────────────────

    #[Test]
    public function продавец_видит_только_своих_лидов(): void
    {
        $sales = $this->admin(AdminAccess::SALES);

        $this->assertTrue($sales->adminScopeIsOwn('leads'));
        $this->assertFalse($sales->adminScopeIsOwn('companies'));
    }

    #[Test]
    public function администратор_видит_всех_лидов(): void
    {
        $this->assertFalse($this->admin(AdminAccess::ADMIN)->adminScopeIsOwn('leads'));
        $this->assertFalse($this->admin(AdminAccess::SUPERADMIN)->adminScopeIsOwn('leads'));
    }

    // ── Личные права ────────────────────────────────────────────────

    #[Test]
    public function личное_право_добавляется_к_роли(): void
    {
        $user = $this->admin(AdminAccess::ADMIN);

        $this->assertFalse($user->hasAdminAbility('payments.view'));

        $user->forceFill(['admin_permissions' => ['grant' => ['payments.view']]])->save();

        $this->assertTrue($user->fresh()->hasAdminAbility('payments.view'));
    }

    #[Test]
    public function личный_отзыв_отбирает_право_роли(): void
    {
        $user = $this->admin(AdminAccess::MODERATOR);

        $this->assertTrue($user->hasAdminAbility('reviews.moderate'));

        $user->forceFill(['admin_permissions' => ['revoke' => ['reviews.moderate']]])->save();

        $this->assertFalse($user->fresh()->hasAdminAbility('reviews.moderate'));
    }

    /** Спорную пару разрешаем в пользу запрета: защита не должна удивлять. */
    #[Test]
    public function отзыв_сильнее_выдачи(): void
    {
        $user = $this->admin(AdminAccess::ADMIN);
        $user->forceFill(['admin_permissions' => [
            'grant' => ['payments.view'],
            'revoke' => ['payments.view'],
        ]])->save();

        $this->assertFalse($user->fresh()->hasAdminAbility('payments.view'));
    }

    /** Суперадмина личный отзыв не трогает: иначе панель можно оставить без владельца. */
    #[Test]
    public function у_суперадмина_право_не_отобрать(): void
    {
        $user = $this->admin(AdminAccess::SUPERADMIN);
        $user->forceFill(['admin_permissions' => ['revoke' => ['settings.view']]])->save();

        $this->assertTrue($user->fresh()->hasAdminAbility('settings.view'));
    }

    // ── Разделы, которых ещё нет ────────────────────────────────────

    /**
     * Суперадмину разрешено и то, чего ещё не построили.
     *
     * Права на CRM, поддержку и возвраты заведены заранее. Если бы
     * суперадмин получал их перечислением, каждый новый раздел
     * пришлось бы отдельно ему выдавать — и однажды забыли бы.
     */
    #[Test]
    public function суперадмин_имеет_права_на_будущие_разделы(): void
    {
        $superadmin = $this->admin(AdminAccess::SUPERADMIN);

        foreach (['leads.view', 'deals.edit', 'support.view', 'refunds.edit', 'audit.view'] as $ability) {
            $this->assertTrue($superadmin->hasAdminAbility($ability), $ability);
        }
    }

    #[Test]
    public function модератор_не_получает_прав_на_crm(): void
    {
        $moderator = $this->admin(AdminAccess::MODERATOR);

        foreach (['leads.view', 'deals.view', 'contacts.view', 'communications.view'] as $ability) {
            $this->assertFalse($moderator->hasAdminAbility($ability), $ability);
        }
    }

    // ── Справочник прав ─────────────────────────────────────────────

    /** Опечатка в названии права не должна тихо превращаться в запрет. */
    #[Test]
    public function несуществующее_право_распознаётся(): void
    {
        $this->assertTrue(AdminAccess::isAbility('companies.view'));
        $this->assertFalse(AdminAccess::isAbility('companys.view'));
        $this->assertFalse(AdminAccess::isAbility('companies.publish'));
    }

    /** Гейт заведён на каждое право: незаведённый вернул бы «нет» и суперадмину. */
    #[Test]
    public function каждое_право_имеет_гейт(): void
    {
        $superadmin = $this->admin(AdminAccess::SUPERADMIN);

        foreach (AdminAccess::all() as $ability) {
            $this->assertTrue($superadmin->can($ability), "гейт «{$ability}» не заведён");
        }
    }

    /** Права выдаются только из справочника: в списке галочек не должно быть выдумок. */
    #[Test]
    public function выдаваемые_права_существуют(): void
    {
        foreach (array_keys(AdminAccess::grantable()) as $ability) {
            $this->assertTrue(AdminAccess::isAbility($ability), $ability);
        }
    }
}
