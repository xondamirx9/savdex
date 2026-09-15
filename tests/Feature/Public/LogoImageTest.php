<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Filament\Resources\Settings\Pages\EditSetting;
use App\Filament\Resources\Settings\Pages\ListSettings;
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
 * Логотип площадки.
 *
 * Знак меняют при ребрендинге, и раньше это означало правку файла
 * в репозитории и выкладку. Теперь он загружается в админке, в разделе
 * «Оформление», — как фон первого экрана. Пустая настройка возвращает
 * знак из репозитория: шапка без логотипа читается как недогрузившаяся
 * страница.
 */
class LogoImageTest extends TestCase
{
    use RefreshDatabase;

    private function setLogo(string $value): void
    {
        Setting::updateOrCreate(
            ['key' => Appearance::KEY_LOGO],
            ['group' => 'appearance', 'label' => 'Логотип площадки', 'type' => 'image', 'value' => $value],
        );

        Setting::flushCache();
    }

    #[Test]
    public function незаполненная_настройка_даёт_знак_из_репозитория(): void
    {
        $this->setLogo('');

        $this->assertSame(Appearance::LOGO_FALLBACK, Appearance::logo());

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('brandLogo', Appearance::LOGO_FALLBACK));
    }

    #[Test]
    public function загруженный_знак_попадает_в_шапку(): void
    {
        $this->setLogo('appearance/znak.svg');

        $this->get('/')->assertInertia(function (AssertableInertia $page): void {
            $url = $page->toArray()['props']['brandLogo'];

            $this->assertStringContainsString('/storage/appearance/znak.svg', $url);
        });
    }

    /** Ссылка на файл в public и внешний адрес берутся как есть. */
    #[Test]
    public function абсолютный_адрес_не_переписывается(): void
    {
        $this->setLogo('/images/logo-mark.svg');
        $this->assertSame('/images/logo-mark.svg', Appearance::logo());

        $this->setLogo('https://cdn.example.com/znak.png');
        $this->assertSame('https://cdn.example.com/znak.png', Appearance::logo());
    }

    /** Настройка живёт в кэше: без сброса правка доехала бы через сутки. */
    #[Test]
    public function смена_знака_видна_сразу(): void
    {
        $this->setLogo('appearance/first.png');
        $this->assertStringContainsString('first.png', Appearance::logo());

        $this->setLogo('appearance/second.png');
        $this->assertStringContainsString('second.png', Appearance::logo());
    }

    /**
     * Фавикон печатает сервер, и тип иконки обязан совпадать с файлом:
     * с чужим type браузер оставляет вкладку с пустым листом.
     */
    #[Test]
    public function фавикон_берёт_загруженный_знак(): void
    {
        $this->setLogo('appearance/znak.png');

        $this->assertNull(Appearance::logoType());
        $this->get('/')->assertSee('/storage/appearance/znak.png', false);

        $this->setLogo('appearance/znak.svg');

        $this->assertSame('image/svg+xml', Appearance::logoType());
        $this->get('/')->assertSee('type="image/svg+xml"', false);
    }

    /**
     * iOS понимает в apple-touch-icon только растр: загруженный
     * вектор она молча игнорирует и рисует снимок страницы.
     */
    #[Test]
    public function иконка_для_экрана_домой_остаётся_растром(): void
    {
        $this->setLogo('appearance/znak.svg');
        $this->assertSame(Appearance::TOUCH_FALLBACK, Appearance::touchIcon());

        $this->setLogo('appearance/znak.png');
        $this->assertStringContainsString('/storage/appearance/znak.png', Appearance::touchIcon());
    }

    /**
     * Загрузка идёт отдельным полем формы: у остальных настроек
     * значение — строка, и общий FileUpload обнулял её.
     */
    #[Test]
    public function знак_загружается_из_админки(): void
    {
        Storage::fake('public');

        $setting = Setting::query()->where('key', Appearance::KEY_LOGO)->firstOrFail();

        Livewire::actingAs($this->admin())
            ->test(EditSetting::class, ['record' => $setting->getRouteKey()])
            ->fillForm(['value_image' => [UploadedFile::fake()->image('znak.png', 512, 512)]])
            ->call('save')
            ->assertHasNoFormErrors();

        Setting::flushCache();

        $saved = (string) Setting::get(Appearance::KEY_LOGO);

        $this->assertNotSame('', $saved, 'Путь к загруженному файлу должен попасть в настройку');
        Storage::disk('public')->assertExists($saved);
        $this->assertStringContainsString('/storage/'.$saved, Appearance::logo());
    }

    /**
     * Знак стоит на размерах от 16 до 360 px сразу, и растр на мелких
     * мылит, поэтому у логотипа — в отличие от фона — принимается вектор.
     */
    #[Test]
    public function вектор_принимается(): void
    {
        Storage::fake('public');

        $setting = Setting::query()->where('key', Appearance::KEY_LOGO)->firstOrFail();

        $svg = UploadedFile::fake()->createWithContent(
            'znak.svg',
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><circle cx="256" cy="256" r="240"/></svg>',
        );

        Livewire::actingAs($this->admin())
            ->test(EditSetting::class, ['record' => $setting->getRouteKey()])
            ->fillForm(['value_image' => [$svg]])
            ->call('save')
            ->assertHasNoFormErrors();

        Setting::flushCache();

        $saved = (string) Setting::get(Appearance::KEY_LOGO);

        $this->assertStringEndsWith('.svg', $saved);
        Storage::disk('public')->assertExists($saved);
    }

    /**
     * Кнопка над списком настроек: знак ищут глазами, а не поиском
     * по ключу среди трёх десятков строк.
     */
    #[Test]
    public function знак_загружается_кнопкой_над_списком(): void
    {
        Storage::fake('public');

        Livewire::actingAs($this->admin())
            ->test(ListSettings::class)
            ->callAction('logo', ['logo' => [UploadedFile::fake()->image('znak.png', 512, 512)]]);

        Setting::flushCache();

        $saved = Appearance::logoPath();

        $this->assertNotSame('', $saved, 'Путь к загруженному файлу должен попасть в настройку');
        Storage::disk('public')->assertExists($saved);
    }

    /**
     * Настройку может удалить администратор — так уже случилось с фоном
     * первого экрана. Кнопка обязана завести строку заново, иначе
     * площадка остаётся без способа сменить знак.
     */
    #[Test]
    public function кнопка_заводит_настройку_заново_если_её_удалили(): void
    {
        Storage::fake('public');

        Setting::query()->where('key', Appearance::KEY_LOGO)->delete();
        Setting::flushCache();

        Livewire::actingAs($this->admin())
            ->test(ListSettings::class)
            ->callAction('logo', ['logo' => [UploadedFile::fake()->image('znak.png', 512, 512)]]);

        Setting::flushCache();

        $setting = Setting::query()->where('key', Appearance::KEY_LOGO)->first();

        $this->assertNotNull($setting, 'Строка настройки должна завестись заново');
        $this->assertSame('appearance', $setting->group);
        $this->assertSame('image', $setting->type);
        $this->assertStringContainsString('/storage/', Appearance::logo());
    }

    /** Пустое поле — вернуть знак из репозитория, а не сломать шапку. */
    #[Test]
    public function пустое_поле_возвращает_знак_по_умолчанию(): void
    {
        $this->setLogo('appearance/znak.png');

        Livewire::actingAs($this->admin())
            ->test(ListSettings::class)
            ->callAction('logo', ['logo' => []]);

        Setting::flushCache();

        $this->assertSame('', Appearance::logoPath());
        $this->assertSame(Appearance::LOGO_FALLBACK, Appearance::logo());
    }

    #[Test]
    public function настройка_заведена_и_видна_в_админке(): void
    {
        $setting = Setting::query()->where('key', Appearance::KEY_LOGO)->first();

        $this->assertNotNull($setting, 'Настройка логотипа должна заводиться миграцией');
        $this->assertSame('image', $setting->type);
        $this->assertSame('appearance', $setting->group);
    }

    private function admin(): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);
    }
}
