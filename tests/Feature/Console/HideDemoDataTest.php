<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\ItTask;
use App\Models\Listing;
use App\Models\Payment;
use App\Models\Review;
use App\Models\User;
use Database\Seeders\CabinetDemoSeeder;
use Database\Seeders\DatabaseSeeder;
use Database\Seeders\DemoSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Миграция hide_demo_data убирает с витрины всё, что демо-сидеры
 * записали в живую базу, и не трогает настоящее.
 *
 * Сценарий — как на боевом до 15.09: в базе настоящие компании
 * (импортированные без сотрудников и зарегистрированные), поверх них
 * отработали демо-сидеры.
 */
class HideDemoDataTest extends TestCase
{
    use RefreshDatabase;

    private function migrate(): void
    {
        $migration = require database_path('migrations/2026_09_29_120000_hide_demo_data.php');
        $migration->up();
    }

    #[Test]
    public function демо_скрыто_настоящее_на_месте(): void
    {
        $this->seed(DatabaseSeeder::class);

        // Настоящие: импортированная без сотрудников и зарегистрированная
        $imported = Company::factory()->create(['name' => 'ООО «Импорт из реестра»']);
        $registered = Company::factory()->create(['name' => 'ООО «Живая фирма»']);
        $owner = User::factory()->for($registered)->create();
        $realListing = Listing::factory()->create([
            'company_id' => $registered->id,
            'title' => 'Кирпич керамический М150',
            'description' => 'Свой кирпич, своё описание.',
        ]);

        $this->seed(DemoSeeder::class);
        Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        $this->seed(CabinetDemoSeeder::class);

        $stroybaza = Company::where('name', 'ООО «Стройбаза»')->sole();
        // Настоящее раскрытие демо-компании — его делал человек
        $realUnlock = ContactUnlock::factory()->create([
            'company_id' => $registered->id,
            'target_company_id' => Company::where('name', 'ООО «Демо-Поставщик»')->value('id'),
            'user_id' => $owner->id,
        ]);
        $realPayment = Payment::create([
            'company_id' => $registered->id, 'description' => 'Пакет 20 кредитов', 'purpose' => 'credits', 'amount' => 100_000,
            'currency' => 'UZS', 'provider' => 'payme', 'status' => 'paid', 'paid_at' => now(),
        ]);

        $this->assertGreaterThan(0, Listing::where('type', 'demand')->where('status', 'active')
            ->whereIn('company_id', [$imported->id, $registered->id])->count(), 'сидер писал заявки от имени настоящих');

        $this->migrate();

        foreach (['ООО «Стройбаза»', 'ООО «Демо-Поставщик»', 'ООО «Демо-Закупщик»', 'IT-студия «Digital Plov»', 'АО «Ферганский цемент»'] as $name) {
            $this->assertSame('blocked', Company::where('name', $name)->value('status'), $name);
        }

        $this->assertSame('active', $imported->fresh()->status);
        $this->assertSame('active', $registered->fresh()->status);
        $this->assertSame('active', $realListing->fresh()->status);

        // Ничего демо на витрине: ни объявлений, ни заявок от имени настоящих, ни задач
        $this->assertSame(0, Listing::where('status', 'active')->where('id', '!=', $realListing->id)->count());
        $this->assertSame(0, ItTask::where('status', 'active')->count());
        $this->assertSame(0, Review::where('status', 'published')->count());

        // Раскрытия сидера удалены, настоящее — нет
        $this->assertSame(0, ContactUnlock::whereNull('user_id')->count());
        $this->assertTrue($realUnlock->fresh() !== null);

        // Демо-платежи не считаются деньгами, настоящий — считается
        $this->assertSame(0, Payment::where('company_id', $stroybaza->id)->where('status', 'paid')->count());
        $this->assertSame('paid', $realPayment->fresh()->status);

        $this->assertSame('blocked', User::where('email', 'demo@savdex.uz')->value('status'));
        $this->assertSame('active', $owner->fresh()->status);

        // Главная — без демо
        $this->get('/')->assertOk()->assertInertia(fn ($page) => $page
            ->where('latest', [])
            ->where('requests', [])
            ->where('reviews', [])
        );
    }

    #[Test]
    public function компания_с_именем_из_демо_но_живыми_людьми_не_трогается(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»']);
        User::factory()->for($company)->create(['email' => 'boss@stroybaza.example']);
        $listing = Listing::factory()->create(['company_id' => $company->id]);

        $this->migrate();

        $this->assertSame('active', $company->fresh()->status);
        $this->assertSame('active', $listing->fresh()->status);
    }
}
