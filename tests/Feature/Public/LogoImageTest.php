<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Setting;
use App\Support\Appearance;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
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

    #[Test]
    public function настройка_заведена_и_видна_в_админке(): void
    {
        $setting = Setting::query()->where('key', Appearance::KEY_LOGO)->first();

        $this->assertNotNull($setting, 'Настройка логотипа должна заводиться миграцией');
        $this->assertSame('image', $setting->type);
        $this->assertSame('appearance', $setting->group);
    }
}
