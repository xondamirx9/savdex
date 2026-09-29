<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Support\Ticket;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Данные компании в настройках профиля.
 *
 * Заполненное меняется раз в полгода и только здесь; пустое можно
 * заполнить когда угодно. Пока срок не вышел — обращение в поддержку.
 */
class CompanyInfoTest extends TestCase
{
    use RefreshDatabase;

    private User $owner;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create([
            'name' => 'ООО «Старое имя»',
            'address' => null,
            'profile_changed_at' => null,
        ]);
        $this->owner = User::factory()->for($this->company)->create([
            'company_role' => 'owner',
            'email_verified_at' => now(),
        ]);
    }

    /** @return array<string, mixed> */
    private function form(array $overrides = []): array
    {
        $c = $this->company->fresh();

        return [
            'name' => $c->name,
            'legal_name' => $c->legal_name,
            'tin' => $c->tin,
            'country_id' => $c->country_id,
            'city_id' => $c->city_id,
            'address' => $c->address,
            'employees_range' => $c->employees_range,
            'founded_year' => $c->founded_year,
            'type' => $c->type,
            'description' => $c->description,
            'is_it_provider' => (bool) $c->is_it_provider,
            'it_specializations' => $c->it_specializations ?? [],
            ...$overrides,
        ];
    }

    #[Test]
    public function владелец_видит_данные_компании(): void
    {
        $this->actingAs($this->owner)
            ->getJson('/cabinet/settings/company-info')
            ->assertOk()
            ->assertJsonPath('company.name', 'ООО «Старое имя»')
            ->assertJsonPath('locked_until', null);
    }

    #[Test]
    public function сотруднику_блок_недоступен(): void
    {
        $staff = User::factory()->for($this->company)->create(['company_role' => 'staff']);

        $this->actingAs($staff)->getJson('/cabinet/settings/company-info')->assertForbidden();
        $this->actingAs($staff)
            ->patchJson('/cabinet/settings/company-info', $this->form(['name' => 'Чужое']))
            ->assertForbidden();
    }

    #[Test]
    public function смена_заполненного_запускает_полгода(): void
    {
        $this->actingAs($this->owner)
            ->patchJson('/cabinet/settings/company-info', $this->form(['name' => 'ООО «Новое имя»']))
            ->assertOk()
            ->assertJsonPath('company.name', 'ООО «Новое имя»');

        $company = $this->company->fresh();
        $this->assertNotNull($company->profile_changed_at);
        $this->assertNotNull($company->profileLockedUntil());

        // Второй раз в тот же срок — отказ, имя прежнее
        $this->actingAs($this->owner)
            ->patchJson('/cabinet/settings/company-info', $this->form(['name' => 'ООО «Третье»']))
            ->assertUnprocessable()
            ->assertJsonValidationErrors('name');

        $this->assertSame('ООО «Новое имя»', $this->company->fresh()->name);
    }

    #[Test]
    public function пустое_заполняется_без_ожидания(): void
    {
        $this->company->forceFill(['profile_changed_at' => now()])->save();

        $this->actingAs($this->owner)
            ->patchJson('/cabinet/settings/company-info', $this->form(['address' => 'Ташкент, ул. Навои, 1']))
            ->assertOk();

        $company = $this->company->fresh();
        $this->assertSame('Ташкент, ул. Навои, 1', $company->address);
        // Заполнение пустого срок не сдвигает
        $this->assertTrue($company->profile_changed_at->isToday());
    }

    #[Test]
    public function через_полгода_менять_снова_можно(): void
    {
        $this->company->forceFill(['profile_changed_at' => now()->subMonths(6)->subDay()])->save();

        $this->actingAs($this->owner)
            ->patchJson('/cabinet/settings/company-info', $this->form(['name' => 'ООО «Через полгода»']))
            ->assertOk()
            ->assertJsonPath('locked_until', fn (string $date): bool => $date !== '');
    }

    #[Test]
    public function обращение_в_поддержку_попадает_в_админку(): void
    {
        $this->company->forceFill(['profile_changed_at' => now()])->save();

        $this->actingAs($this->owner)
            ->postJson('/cabinet/settings/company-info/support', ['message' => 'Сменился юридический адрес, нужно обновить.'])
            ->assertOk();

        $ticket = Ticket::query()->with('messages')->sole();
        $this->assertSame($this->company->id, $ticket->company_id);
        $this->assertSame($this->owner->id, $ticket->user_id);
        $this->assertSame(Ticket::STATUS_OPEN, $ticket->status);
        $this->assertStringContainsString('Сменился юридический адрес', $ticket->messages->first()->body);
    }

    #[Test]
    public function пустое_обращение_не_отправляется(): void
    {
        $this->actingAs($this->owner)
            ->postJson('/cabinet/settings/company-info/support', ['message' => ''])
            ->assertJsonValidationErrors('message');

        $this->assertSame(0, Ticket::query()->count());
    }

    /**
     * Страница «Компания» заполненное не меняет — иначе полгода
     * обходились бы одной формой.
     */
    #[Test]
    public function страница_компании_не_меняет_заполненное(): void
    {
        $this->actingAs($this->owner)
            ->from('/cabinet/company')
            ->patch('/cabinet/company', $this->form(['name' => 'ООО «В обход»']))
            ->assertSessionHasErrors('name');

        $this->assertSame('ООО «Старое имя»', $this->company->fresh()->name);
    }

    #[Test]
    public function страница_компании_заполняет_пустое(): void
    {
        $this->actingAs($this->owner)
            ->from('/cabinet/company')
            ->patch('/cabinet/company', $this->form(['address' => 'Самарканд', 'website' => 'firma.uz']))
            ->assertSessionHasNoErrors();

        $company = $this->company->fresh();
        $this->assertSame('Самарканд', $company->address);
        $this->assertSame('firma.uz', $company->website);
        $this->assertNull($company->profile_changed_at);
    }
}
