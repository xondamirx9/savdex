<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Управление контактами компании из кабинета: сменить телефон,
 * добавить новый, удалить лишний. Ровно тот сценарий, с которым
 * пришла клиентка: указала номер при регистрации и не могла сменить.
 */
class CompanyContactManageTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);
    }

    private function phone(string $value = '+998 90 111-22-33'): CompanyContact
    {
        return $this->company->contacts()->create([
            'type' => CompanyContact::TYPE_PHONE,
            'value' => $value,
            'is_public' => true,
        ]);
    }

    #[Test]
    public function номер_телефона_меняется(): void
    {
        $contact = $this->phone();

        $this->actingAs($this->user)
            ->patch("/cabinet/company/contacts/{$contact->id}", [
                'type' => 'phone',
                'value' => '+998 90 999-88-77',
            ])
            ->assertRedirect()
            ->assertSessionHasNoErrors();

        $this->assertSame('+998 90 999-88-77', $contact->fresh()->value);
    }

    #[Test]
    public function кривой_номер_отклоняется(): void
    {
        $contact = $this->phone();

        $this->actingAs($this->user)
            ->patch("/cabinet/company/contacts/{$contact->id}", [
                'type' => 'phone',
                'value' => 'позвоните мне',
            ])
            ->assertSessionHasErrors('value');

        $this->assertSame('+998 90 111-22-33', $contact->fresh()->value);
    }

    #[Test]
    public function контакт_добавляется_и_удаляется(): void
    {
        $first = $this->phone();

        $this->actingAs($this->user)
            ->post('/cabinet/company/contacts', [
                'type' => 'phone',
                'value' => '+998 71 200-45-80',
                'label' => 'Отдел продаж',
            ])
            ->assertSessionHasNoErrors();

        $this->assertSame(2, $this->company->contacts()->count());

        $this->actingAs($this->user)
            ->delete("/cabinet/company/contacts/{$first->id}")
            ->assertSessionHasNoErrors();

        $this->assertSame(1, $this->company->contacts()->count());
    }

    /** Компания без единого телефона и почты — недостижима: последний не удаляется. */
    #[Test]
    public function последний_способ_связи_не_удаляется(): void
    {
        $contact = $this->phone();

        $this->actingAs($this->user)
            ->delete("/cabinet/company/contacts/{$contact->id}")
            ->assertSessionHas('error');

        $this->assertSame(1, $this->company->contacts()->count());
    }

    #[Test]
    public function чужой_контакт_не_редактируется(): void
    {
        $contact = $this->phone();

        $stranger = User::factory()->for(Company::factory()->create())->create(['email_verified_at' => now()]);

        $this->actingAs($stranger)
            ->patch("/cabinet/company/contacts/{$contact->id}", ['type' => 'phone', 'value' => '+998 90 000-00-00'])
            ->assertNotFound();
    }
}
