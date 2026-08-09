<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\ContactUnlock;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Доступ к контактам на визитке — ядро монетизации (§3 ТЗ).
 *
 * Ошибка здесь стоит денег в обе стороны: закрытый оплаченный контакт
 * — это возврат и жалоба, открытый неоплаченный — потерянная выручка.
 */
class ContactAccessTest extends TestCase
{
    use RefreshDatabase;

    private function companyWithPhone(string $name = 'ООО «Поставщик»'): Company
    {
        $company = Company::factory()->create(['name' => $name]);

        CompanyContact::create([
            'company_id' => $company->id,
            'type' => 'phone',
            'value' => '+998 90 555-11-22',
            'is_public' => true,
            'is_primary' => true,
        ]);

        return $company;
    }

    #[Test]
    public function гость_видит_только_маску(): void
    {
        $company = $this->companyWithPhone();

        $this->get("/company/{$company->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('unlocked', false)
                ->where('contacts.0.locked', true)
                ->where('contacts.0.href', null),
            )
            ->assertDontSee('555-11-22');
    }

    #[Test]
    public function открытый_контакт_виден_целиком_и_навсегда(): void
    {
        $supplier = $this->companyWithPhone();
        $buyerCompany = Company::factory()->create(['name' => 'ООО «Покупатель»']);
        $buyer = User::factory()->create(['company_id' => $buyerCompany->id]);

        ContactUnlock::create([
            'company_id' => $buyerCompany->id,
            'target_company_id' => $supplier->id,
            'credits_spent' => 1,
        ]);

        $this->actingAs($buyer)
            ->get("/company/{$supplier->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('unlocked', true)
                ->where('is_own', false)
                ->where('contacts.0.locked', false)
                ->where('contacts.0.value', '+998 90 555-11-22')
                ->where('locked_count', 0),
            );
    }

    /**
     * Раскрытие односторонее.
     *
     * То, что кто-то открыл ваши контакты («кто мной интересуется»),
     * не открывает вам его контакты. Иначе одна оплата работала бы
     * в обе стороны и половина раскрытий стала бы бесплатной.
     */
    #[Test]
    public function раскрытие_не_работает_в_обратную_сторону(): void
    {
        $supplier = $this->companyWithPhone();
        $buyerCompany = Company::factory()->create();
        $buyer = User::factory()->create(['company_id' => $buyerCompany->id]);

        // Покупатель открыл контакты поставщика
        ContactUnlock::create([
            'company_id' => $buyerCompany->id,
            'target_company_id' => $supplier->id,
            'credits_spent' => 1,
        ]);

        CompanyContact::create([
            'company_id' => $buyerCompany->id,
            'type' => 'phone',
            'value' => '+998 71 000-00-00',
            'is_public' => true,
        ]);

        $supplierUser = User::factory()->create(['company_id' => $supplier->id]);

        // Поставщик смотрит визитку покупателя — контакты закрыты
        $this->actingAs($supplierUser)
            ->get("/company/{$buyerCompany->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('unlocked', false)
                ->where('contacts.0.locked', true),
            );
    }

    #[Test]
    public function свои_контакты_видны_всегда(): void
    {
        $company = $this->companyWithPhone();
        $employee = User::factory()->create(['company_id' => $company->id]);

        $this->actingAs($employee)
            ->get("/company/{$company->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('unlocked', true)
                ->where('is_own', true),
            );
    }

    /**
     * Сайт компании не скрывается: он и так публичен, а замок на нём
     * выглядит жадностью и портит доверие ко всей карточке.
     */
    #[Test]
    public function сайт_компании_не_скрывается(): void
    {
        $company = Company::factory()->create();

        CompanyContact::create([
            'company_id' => $company->id,
            'type' => CompanyContact::TYPE_WEBSITE,
            'value' => 'stroybaza.uz',
            'is_public' => true,
        ]);

        $this->get("/company/{$company->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('contacts.0.locked', false)
                ->where('locked_count', 0),
            );
    }
}
