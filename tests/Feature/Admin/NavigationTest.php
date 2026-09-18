<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Widgets\PlatformStats;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Facades\Filament;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Меню панели по ролям.
 *
 * Права проверяются отдельно, поресурсно. Здесь проверяется то, что
 * человек видит на самом деле, открыв панель: собранное меню целиком.
 * Между «право закрыто» и «пункта нет в меню» стоит регистрация
 * ресурсов, группы и виджеты, и ошибиться можно в любом из них.
 *
 * Каждая роль — отдельный тест: Filament собирает меню один раз за
 * процесс, и в цикле все роли получили бы список первой.
 */
class NavigationTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Ожидаемое меню каждой роли, по группам.
     *
     * Списки записаны руками. Тест, который спрашивает матрицу, что она
     * разрешает, и сверяет ответ с ней же, не проверяет ничего.
     *
     * @return array<string, array{string, array<string, list<string>>}>
     */
    public static function менюРолей(): array
    {
        $crm = ['Лиды', 'Сделки', 'Контакты', 'Задачи', 'Коммуникации'];

        return [
            'Администратор' => [AdminAccess::ADMIN, [
                'CRM' => $crm,
                'Поддержка' => ['Обращения'],
                'Контент' => ['Главная страница', 'Новости', 'Страницы и FAQ', 'Тендеры', 'Баннеры'],
                'Модерация' => ['Отзывы', 'Жалобы на контакты', 'Документы на проверку', 'Резюме'],
                'Данные' => ['Компании', 'Объявления', 'IT-задачи'],
                'Справочники' => ['Категории', 'Типы компаний', 'Страны', 'Города'],
                'Система' => ['Пользователи', 'Рассылки', 'Журнал действий'],
            ]],

            'Отдел продаж' => [AdminAccess::SALES, [
                'CRM' => $crm,
                'Контент' => ['Тендеры'],
                'Монетизация' => ['Промокоды'],
                'Данные' => ['Компании', 'Объявления'],
            ]],

            'Менеджер поставщиков' => [AdminAccess::SUPPLIER_MANAGER, [
                'CRM' => $crm,
                'Контент' => ['Тендеры'],
                'Модерация' => ['Документы на проверку'],
                'Данные' => ['Компании', 'Объявления'],
            ]],

            'Менеджер покупателей' => [AdminAccess::BUYER_MANAGER, [
                'CRM' => $crm,
                'Контент' => ['Тендеры'],
                'Модерация' => ['Документы на проверку'],
                'Данные' => ['Компании', 'Объявления'],
            ]],

            'Модератор' => [AdminAccess::MODERATOR, [
                'Контент' => ['Тендеры'],
                'Модерация' => ['Отзывы', 'Жалобы на контакты', 'Документы на проверку', 'Резюме'],
                'Данные' => ['Компании', 'Объявления', 'IT-задачи'],
                'Справочники' => ['Категории', 'Типы компаний', 'Страны', 'Города'],
            ]],

            'Финансы' => [AdminAccess::FINANCE, [
                'Монетизация' => [
                    'Тарифы', 'Подписки', 'Счета и оплаты',
                    'Возвраты', 'Финансовые операции', 'Пакеты контактов', 'Промокоды',
                    'Финансовые отчёты', 'Сверка со шлюзом',
                ],
                'Данные' => ['Компании'],
                'Система' => ['Журнал действий'],
            ]],

            'Поддержка' => [AdminAccess::SUPPORT, [
                'CRM' => ['Контакты', 'Задачи', 'Коммуникации'],
                'Поддержка' => ['Обращения'],
                'Модерация' => ['Отзывы', 'Жалобы на контакты', 'Резюме'],
                'Монетизация' => ['Подписки'],
                'Данные' => ['Компании', 'Объявления', 'IT-задачи'],
                'Система' => ['Пользователи'],
            ]],

            'Контент-менеджер' => [AdminAccess::CONTENT_MANAGER, [
                'Контент' => ['Главная страница', 'Новости', 'Страницы и FAQ', 'Баннеры'],
                'Справочники' => ['Категории', 'Типы компаний', 'Страны', 'Города'],
                'Система' => ['Рассылки'],
            ]],
        ];
    }

    private function actAs(string $role): User
    {
        $user = User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);

        $this->actingAs($user);

        return $user;
    }

    /**
     * @return array<string, list<string>>
     */
    private function menu(): array
    {
        $panel = Filament::getPanel('admin');
        Filament::setCurrentPanel($panel);

        $menu = [];

        foreach ($panel->getNavigation() as $group) {
            $label = (string) $group->getLabel();

            $items = collect($group->getItems())
                ->map(fn ($item): string => (string) $item->getLabel())
                ->reject(fn (string $item): bool => $item === 'Инфопанель')
                ->values()
                ->all();

            if ($items !== []) {
                $menu[$label] = $items;
            }
        }

        return $menu;
    }

    /**
     * @param  array<string, list<string>>  $expected
     */
    #[Test]
    #[DataProvider('менюРолей')]
    public function роль_видит_ровно_своё_меню(string $role, array $expected): void
    {
        $this->actAs($role);

        $this->assertSame($expected, $this->menu());
    }

    #[Test]
    public function суперадмин_видит_все_группы(): void
    {
        $this->actAs(AdminAccess::SUPERADMIN);

        $this->assertSame([
            'CRM', 'Поддержка', 'Контент', 'Модерация',
            'Монетизация', 'Данные', 'Справочники', 'Система',
        ], array_keys($this->menu()));
    }

    // ── Дашборд ─────────────────────────────────────────────────────

    /**
     * Выручка на первом экране — только тем, кому положены финансы.
     *
     * У продавца, поддержки, модератора и контент-менеджера в границах
     * роли записано «не видит финансовую аналитику», а дашборд
     * открывался всем одинаковый: раздел закрыт, а цифра из него на
     * виду. Утечка, оформленная как удобство.
     */
    #[Test]
    public function выручку_на_дашборде_видят_только_финансы(): void
    {
        foreach (AdminAccess::ROLES as $role => $label) {
            $this->actAs($role);

            $rendered = Livewire::test(PlatformStats::class);

            // Проверяется отрисованный виджет, а не внутренний список:
            // человек видит именно это
            if (in_array($role, [AdminAccess::SUPERADMIN, AdminAccess::FINANCE], true)) {
                $rendered->assertSee('Выручка', escape: false);
            } else {
                $rendered->assertDontSee('Выручка', escape: false);
            }
        }
    }
}
