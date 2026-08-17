<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Companies\Pages\EditCompany;
use App\Filament\Resources\Listings\Pages\EditListing;
use App\Filament\Resources\Settings\Pages\EditSetting;
use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use App\Models\Setting;
use App\Models\User;
use App\Support\OfficeLocation;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Формы редактирования в админке.
 *
 * У компаний и объявлений схемы форм остались заглушками с одним
 * комментарием внутри: экран правки открывался пустым — заголовок,
 * кнопка «Сохранить» и ничего между ними. Тест проверяет не вёрстку,
 * а то, что поля доходят до формы и записываются обратно.
 */
class AdminFormsTest extends TestCase
{
    use RefreshDatabase;

    private function superadmin(): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);
    }

    #[Test]
    public function форма_компании_открывается_с_данными_и_сохраняет(): void
    {
        $this->actingAs($this->superadmin());

        $company = Company::factory()->create([
            'name' => 'ООО «Стройбаза»',
            'tin' => '304561278',
            'type' => 'distributor',
        ]);

        Livewire::test(EditCompany::class, ['record' => $company->getRouteKey()])
            ->assertFormSet([
                'name' => 'ООО «Стройбаза»',
                'tin' => '304561278',
                'type' => 'distributor',
            ])
            ->fillForm(['tin' => '304561279', 'address' => 'г. Ташкент, ул. Амира Темура, 1'])
            ->call('save')
            ->assertHasNoFormErrors();

        $company->refresh();

        $this->assertSame('304561279', $company->tin);
        $this->assertSame('г. Ташкент, ул. Амира Темура, 1', $company->address);
    }

    #[Test]
    public function форма_объявления_открывается_с_данными_и_сохраняет(): void
    {
        $this->actingAs($this->superadmin());

        $listing = Listing::factory()->create([
            'title' => 'Кирпич керамический полнотелый М150',
            'status' => Listing::STATUS_MODERATION,
        ]);

        Livewire::test(EditListing::class, ['record' => $listing->getRouteKey()])
            ->assertFormSet(['title' => 'Кирпич керамический полнотелый М150'])
            ->fillForm(['title' => 'Кирпич керамический полнотелый М200'])
            ->call('save')
            ->assertHasNoFormErrors();

        $this->assertSame('Кирпич керамический полнотелый М200', $listing->fresh()->title);
    }

    /**
     * Заметка модерации — единственное поле формы, которого не было
     * в списке заполняемых. Без него текст отказа молча пропадал бы
     * при сохранении, а владелец объявления так и не узнал бы причину.
     */
    #[Test]
    public function заметка_модерации_сохраняется(): void
    {
        $this->actingAs($this->superadmin());

        $listing = Listing::factory()->create(['status' => Listing::STATUS_REJECTED]);

        Livewire::test(EditListing::class, ['record' => $listing->getRouteKey()])
            ->fillForm(['moderation_note' => 'Уберите номер телефона из описания'])
            ->call('save')
            ->assertHasNoFormErrors();

        $this->assertSame('Уберите номер телефона из описания', $listing->fresh()->moderation_note);
    }

    /** Пустая цена допустима только вместе с отметкой «договорная». */
    #[Test]
    public function цена_обязательна_если_она_не_договорная(): void
    {
        $this->actingAs($this->superadmin());

        $listing = Listing::factory()->create(['price' => 100, 'price_negotiable' => false]);

        Livewire::test(EditListing::class, ['record' => $listing->getRouteKey()])
            ->fillForm(['price' => null, 'price_negotiable' => false])
            ->call('save')
            ->assertHasFormErrors(['price']);
    }

    /**
     * Объявление заводит компания: у него есть владелец, автор и слот
     * в тарифе. Созданное из админки не принадлежало бы никому.
     */
    #[Test]
    public function объявление_из_админки_не_создаётся(): void
    {
        $this->actingAs($this->superadmin());

        $this->get('/admin/listings/create')->assertNotFound();
    }

    /** Категории в форме показываются вместе с разделом-родителем. */
    #[Test]
    public function категории_в_форме_показывают_родителя(): void
    {
        $this->actingAs($this->superadmin());

        $parent = Category::factory()->named('Стройматериалы')->create();
        $child = Category::factory()->child($parent)->named('Кирпич')->create();

        $listing = Listing::factory()->create(['category_id' => $child->id]);

        Livewire::test(EditListing::class, ['record' => $listing->getRouteKey()])
            ->assertSee('Стройматериалы → Кирпич');
    }

    // ── Настройки площадки ───────────────────────────────────

    /** Часть настроек заводит миграция — поэтому updateOrCreate, а не create. */
    private function setting(string $key, string $value): Setting
    {
        return Setting::updateOrCreate(
            ['key' => $key],
            ['group' => 'contacts', 'label' => $key, 'type' => 'string', 'value' => $value],
        );
    }

    /** Координаты офиса правятся в админке — ради этого настройка и заведена. */
    #[Test]
    public function координаты_офиса_сохраняются_из_админки(): void
    {
        $this->actingAs($this->superadmin());

        $setting = $this->setting(OfficeLocation::KEY_COORDS, '41.311081, 69.240562');

        Livewire::test(EditSetting::class, ['record' => $setting->getRouteKey()])
            ->assertFormSet(['value' => '41.311081, 69.240562'])
            ->fillForm(['value' => '39.654620, 66.959720'])
            ->call('save')
            ->assertHasNoFormErrors();

        $this->assertSame([39.65462, 66.95972], OfficeLocation::coords((string) $setting->refresh()->value));
    }

    /**
     * Опечатка в координатах ловится формой. Без проверки карта на
     * странице «О компании» просто пропадала бы — молча и уже после
     * сохранения, так что связать пропажу с правкой было бы некому.
     */
    #[Test]
    public function испорченные_координаты_офиса_не_сохраняются(): void
    {
        $this->actingAs($this->superadmin());

        $setting = $this->setting(OfficeLocation::KEY_COORDS, '41.311081, 69.240562');

        Livewire::test(EditSetting::class, ['record' => $setting->getRouteKey()])
            ->fillForm(['value' => '41,31 69,24'])
            ->call('save')
            ->assertHasFormErrors(['value']);

        $this->assertSame('41.311081, 69.240562', $setting->refresh()->value);
    }

    /** Проверка координат не должна мешать остальным строковым настройкам. */
    #[Test]
    public function прочие_настройки_сохраняются_свободным_текстом(): void
    {
        $this->actingAs($this->superadmin());

        $setting = $this->setting('support_phone', '+998 71 200-00-00');

        Livewire::test(EditSetting::class, ['record' => $setting->getRouteKey()])
            ->fillForm(['value' => '+998 71 300-00-00'])
            ->call('save')
            ->assertHasNoFormErrors();

        $this->assertSame('+998 71 300-00-00', $setting->refresh()->value);
    }
}
