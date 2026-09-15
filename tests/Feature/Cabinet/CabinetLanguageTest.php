<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\CompanyDocument;
use App\Models\User;
use App\Support\Locales;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Кабинет на выбранном языке.
 *
 * Словарь интерфейса живёт во фронтенде, но часть подписей собирает
 * сервер: вкладки объявлений, периоды аналитики, чек-лист верификации,
 * типы файлов. Эти строки словарь React не догонит — они приходят
 * готовыми в пропсах, и раньше приходили по-русски при любом языке.
 */
class CabinetLanguageTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $company = Company::factory()->create();
        $this->user = User::factory()->for($company)->create();
    }

    /** @return list<array{string}> */
    public static function языки(): array
    {
        return array_map(fn (string $code): array => [$code], Locales::codes());
    }

    #[Test]
    #[DataProvider('языки')]
    public function вкладки_объявлений_приходят_на_языке_сайта(string $locale): void
    {
        $this->actingAs($this->user)
            ->get(Locales::url('/cabinet/listings', $locale))
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('tabs.active', __('ui.cabinet.listings.tab_active', locale: $locale))
                ->where('tabs.draft', __('ui.cabinet.listings.tab_draft', locale: $locale))
                ->etc());
    }

    #[Test]
    #[DataProvider('языки')]
    public function периоды_аналитики_приходят_на_языке_сайта(string $locale): void
    {
        $this->actingAs($this->user)
            ->get(Locales::url('/cabinet/analytics', $locale))
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('periods.30', __('ui.cabinet.analytics.period_days', ['days' => 30], $locale))
                ->etc());
    }

    #[Test]
    #[DataProvider('языки')]
    public function чек_лист_верификации_приходит_на_языке_сайта(string $locale): void
    {
        $this->actingAs($this->user)
            ->get(Locales::url('/cabinet/company', $locale))
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('verification.0.label', __('ui.cabinet.company.verify_email', locale: $locale))
                ->where('employees.0.role', __('ui.cabinet.company.role_owner', locale: $locale))
                ->etc());
    }

    /**
     * Тип файла — подпись из словаря, а не значение из базы: в базе
     * лежит код, и при смене языка он обязан меняться вместе с сайтом.
     */
    #[Test]
    #[DataProvider('языки')]
    public function тип_файла_переводится(string $locale): void
    {
        $document = new CompanyDocument(['type' => 'price_list']);

        app()->setLocale($locale);

        $this->assertSame(
            __('ui.cabinet.files.types.price_list', locale: $locale),
            $document->typeLabel(),
        );
    }
}
