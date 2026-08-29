<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Доступ к кабинету и его разделам.
 *
 * Появился после ручного прохода, вскрывшего сразу три дыры:
 * — публикация открывалась по прямой ссылке без подтверждённой почты;
 * — разделы бокового меню вели на несуществующие маршруты;
 * — сообщение о смене пароля терялось по дороге к форме входа.
 */
class CabinetAccessTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function гость_отправляется_на_вход(): void
    {
        $this->get('/cabinet')->assertRedirect('/login');
    }

    /**
     * Кабинет говорит о блокировке компании прямо: объявления при ней
     * значатся активными, но витрина их прячет — без предупреждения
     * владелец ищет поломку вместо причины.
     */
    #[Test]
    public function кабинет_сообщает_о_блокировке_компании(): void
    {
        $company = Company::factory()->blocked()->create();
        $user = User::factory()->for($company)->create(['email_verified_at' => now()]);

        $this->actingAs($user)->get('/cabinet')
            ->assertOk()
            ->assertInertia(fn ($page) => $page
                ->where('auth.company.blocked', true));
    }

    #[Test]
    public function неподтверждённая_почта_не_мешает_войти_в_кабинет(): void
    {
        /*
         * Намеренно: полная блокировка кабинета до подтверждения почты
         * убивает конверсию регистрации. Закрыты только публикация
         * и раскрытие контактов (§5.1 FR-AUTH-02 ТЗ).
         */
        $user = User::factory()->unverified()->create();

        $this->actingAs($user)
            ->get('/cabinet')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('cabinet/Dashboard')
                ->where('auth.user.email_verified', false),
            );
    }

    #[Test]
    public function публикация_закрыта_до_подтверждения_почты(): void
    {
        $user = User::factory()->unverified()->create();

        // Скрыть кнопку в интерфейсе мало: адрес открывается напрямую
        $this->actingAs($user)
            ->get('/cabinet/listings/create')
            ->assertRedirect('/verify-email');
    }

    /**
     * Без компании публиковать нельзя: объявление выходит от её имени,
     * и покупатель должен видеть, с кем имеет дело.
     */
    #[Test]
    public function публикация_без_компании_ведёт_к_заполнению_карточки(): void
    {
        $this->actingAs(User::factory()->create())
            ->get('/cabinet/listings/create')
            ->assertRedirect('/cabinet/company');
    }

    /**
     * У компании мастер сразу создаёт черновик и открывает его:
     * автосохранение обещано в интерфейсе, а сохранять некуда,
     * пока записи нет.
     */
    #[Test]
    public function публикация_открыта_после_подтверждения(): void
    {
        // Тариф Free обязан существовать: на него опирается расчёт
        // лимитов для компаний без подписки
        $this->seed(PlanSeeder::class);

        $user = User::factory()->for(Company::factory())->create();

        $response = $this->actingAs($user)->get('/cabinet/listings/create');

        $listing = $user->company->listings()->first();

        $this->assertNotNull($listing, 'Черновик должен создаваться сразу');
        $this->assertSame(Listing::STATUS_DRAFT, $listing->status);

        $response->assertRedirect("/cabinet/listings/{$listing->id}/edit");
    }

    /** @return list<array{string}> */
    public static function разделыКабинета(): array
    {
        return [
            ['/cabinet/listings'],
            ['/cabinet/company'],
            ['/cabinet/contacts'],
            ['/cabinet/billing'],
            ['/cabinet/reviews'],
            ['/cabinet/settings'],
        ];
    }

    /**
     * Каждый пункт бокового меню должен открываться.
     * Ссылка на несуществующий маршрут роняет страницу с 500 —
     * тот же класс ошибки, что и verification.verify.
     */
    #[Test]
    #[DataProvider('разделыКабинета')]
    public function раздел_кабинета_открывается(string $url): void
    {
        $this->actingAs(User::factory()->create())->get($url)->assertOk();
    }

    #[Test]
    public function сводка_отдаёт_показатели_и_лимиты(): void
    {
        $this->seed(PlanSeeder::class);

        $user = User::factory()->for(Company::factory())->create();

        $this->actingAs($user)
            ->get('/cabinet')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('metrics.impressions.value')
                ->has('metrics.views.value')
                ->has('metrics.unlocks.value')
                ->has('metrics.conversion.value')
                ->has('series.impressions')
                ->has('limits.listings.used')
                ->where('plan.name', 'Free')
                ->has('company.completeness'),
            );
    }

    /**
     * Без компании дашборд не падает, а зовёт заполнить карточку:
     * это первый экран после регистрации, и ошибка на нём читается
     * как поломка всего кабинета.
     */
    #[Test]
    public function сводка_без_компании_не_падает(): void
    {
        $this->actingAs(User::factory()->create())
            ->get('/cabinet')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->where('company', null));
    }

    #[Test]
    public function выход_завершает_сессию(): void
    {
        $this->actingAs(User::factory()->create())
            ->post('/logout')
            ->assertRedirect('/');

        $this->assertGuest();
    }
}
