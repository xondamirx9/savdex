<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Filament\Resources\Settings\Pages\EditSetting;
use App\Models\Setting;
use App\Models\User;
use App\Support\Appearance;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
use Inertia\Testing\AssertableInertia;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Фон первого экрана главной.
 *
 * Картинку меняют в админке, в разделе «Оформление», — витрина
 * обязана подхватывать её без пересборки стилей. Пустая настройка
 * возвращает картинку из коробки: первый экран без фона выглядит
 * как поломка, а не как «фон не выбран».
 */
class HeroImageTest extends TestCase
{
    use RefreshDatabase;

    private function setHero(string $value): void
    {
        Setting::updateOrCreate(
            ['key' => Appearance::KEY_HERO],
            ['group' => 'appearance', 'label' => 'Фон первого экрана', 'type' => 'image', 'value' => $value],
        );

        Setting::flushCache();
    }

    #[Test]
    public function незаполненная_настройка_даёт_картинку_из_коробки(): void
    {
        $this->setHero('');

        $this->assertSame(Appearance::HERO_FALLBACK, Appearance::heroImage());

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('heroImage', Appearance::HERO_FALLBACK));
    }

    #[Test]
    public function загруженная_картинка_попадает_на_главную(): void
    {
        $this->setHero('appearance/fon.jpg');

        $this->get('/')->assertInertia(function (AssertableInertia $page): void {
            $url = $page->toArray()['props']['heroImage'];

            $this->assertStringContainsString('/storage/appearance/fon.jpg', $url);
        });
    }

    /** Ссылка на файл в public и внешний адрес берутся как есть. */
    #[Test]
    public function абсолютный_адрес_не_переписывается(): void
    {
        $this->setHero('/images/hero-port.svg');
        $this->assertSame('/images/hero-port.svg', Appearance::heroImage());

        $this->setHero('https://cdn.example.com/fon.jpg');
        $this->assertSame('https://cdn.example.com/fon.jpg', Appearance::heroImage());
    }

    /** Настройка живёт в кэше: без сброса правка доехала бы через сутки. */
    #[Test]
    public function смена_картинки_видна_сразу(): void
    {
        $this->setHero('appearance/first.jpg');
        $this->assertStringContainsString('first.jpg', Appearance::heroImage());

        $this->setHero('appearance/second.jpg');
        $this->assertStringContainsString('second.jpg', Appearance::heroImage());
    }

    /**
     * Загрузка идёт отдельным полем формы: у остальных настроек
     * значение — строка, и общий FileUpload обнулял её.
     */
    #[Test]
    public function картинка_загружается_из_админки(): void
    {
        $admin = User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);

        Storage::fake('public');

        $setting = Setting::query()->where('key', Appearance::KEY_HERO)->firstOrFail();

        Livewire::actingAs($admin)
            ->test(EditSetting::class, ['record' => $setting->getRouteKey()])
            ->fillForm(['value_image' => [UploadedFile::fake()->image('fon.jpg', 1920, 1080)]])
            ->call('save')
            ->assertHasNoFormErrors();

        Setting::flushCache();

        $saved = (string) Setting::get(Appearance::KEY_HERO);

        $this->assertNotSame('', $saved, 'Путь к загруженному файлу должен попасть в настройку');
        Storage::disk('public')->assertExists($saved);
        $this->assertStringContainsString('/storage/'.$saved, Appearance::heroImage());
    }

    #[Test]
    public function настройка_заведена_и_видна_в_админке(): void
    {
        $setting = Setting::query()->where('key', Appearance::KEY_HERO)->first();

        $this->assertNotNull($setting, 'Настройка фона должна заводиться миграцией');
        $this->assertSame('image', $setting->type);
        $this->assertSame('appearance', $setting->group);
        $this->assertArrayHasKey('appearance', Setting::GROUPS);
    }
}
