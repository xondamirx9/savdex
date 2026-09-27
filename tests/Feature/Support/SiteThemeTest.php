<?php

declare(strict_types=1);

namespace Tests\Feature\Support;

use App\Support\Microsite\SiteHost;
use App\Support\Microsite\SiteTheme;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Оформление мини-сайта: что бы ни выбрала компания, страница
 * остаётся читаемой, а в <style> попадают только проверенные значения.
 */
class SiteThemeTest extends TestCase
{
    #[Test]
    public function неизвестное_заменяется_значениями_по_умолчанию(): void
    {
        $theme = SiteTheme::normalize([
            'template' => 'custom',
            'primary' => 'red;}body{display:none',
            'heading_font' => 'Comic Sans',
            'radius' => 'huge',
            'css' => 'body{}',
        ]);

        $this->assertSame(SiteTheme::DEFAULTS, $theme);
    }

    #[Test]
    public function кнопка_получает_читаемый_текст(): void
    {
        $this->assertSame('#ffffff', SiteTheme::readableOn('#1a56db'));
        $this->assertSame('#0f172a', SiteTheme::readableOn('#facc15'));
    }

    /** Жёлтый бренд на белом фоне для ссылок затемняется до AA. */
    #[Test]
    public function светлый_бренд_затемняется_для_текста(): void
    {
        $vars = SiteTheme::variables(SiteTheme::normalize(['primary' => '#facc15']));

        $this->assertNotSame('#facc15', $vars['--ms-primary-text']);
        $this->assertGreaterThanOrEqual(4.5, SiteTheme::contrast($vars['--ms-primary-text'], $vars['--ms-bg']));
        // Сама кнопка остаётся фирменного цвета
        $this->assertSame('#facc15', $vars['--ms-primary']);
    }

    #[Test]
    public function все_пресеты_читаемы_в_своей_теме(): void
    {
        foreach (SiteTheme::PRESETS as $name => $preset) {
            $vars = SiteTheme::variables(SiteTheme::normalize($preset));

            $this->assertGreaterThanOrEqual(4.5, SiteTheme::contrast($vars['--ms-primary-text'], $vars['--ms-bg']), $name);
            $this->assertGreaterThanOrEqual(4.5, SiteTheme::contrast($vars['--ms-text'], $vars['--ms-bg']), $name);
        }
    }

    #[Test]
    public function шрифты_одним_запросом(): void
    {
        $url = SiteTheme::fontsUrl(SiteTheme::normalize(['heading_font' => 'lora', 'body_font' => 'pt-sans']));

        $this->assertSame('https://fonts.bunny.net/css?family=lora:400,600,700|pt-sans:400,600,700&display=swap', $url);
    }

    #[Test]
    public function поддомен_из_хоста(): void
    {
        $this->assertSame('acme', SiteHost::subdomain('acme.savdex.site'));
        $this->assertSame('acme', SiteHost::subdomain('ACME.savdex.site'));
        $this->assertNull(SiteHost::subdomain('a.b.savdex.site'));
        $this->assertNull(SiteHost::subdomain('savdex.site'));
        $this->assertNull(SiteHost::subdomain('acme.savdex.uz'));
        $this->assertTrue(SiteHost::matches('savdex.site'));
        $this->assertFalse(SiteHost::matches('notsavdex.site'));
    }

    /** Без домена ни один хост не считается доменом мини-сайтов. */
    #[Test]
    public function без_домена_хосты_не_ограничиваются(): void
    {
        config(['microsite.domain' => null]);

        $this->assertFalse(SiteHost::usesSubdomains());
        $this->assertFalse(SiteHost::matches('savdex.site'));
        $this->assertFalse(SiteHost::matches('localhost'));
        $this->assertNull(SiteHost::subdomain('acme.savdex.site'));
    }

    #[Test]
    public function предложенный_адрес_проходит_проверку(): void
    {
        foreach (['ooo-akme-treyd', 'a', 'x--y', str_repeat('long-', 20)] as $slug) {
            $this->assertMatchesRegularExpression(SiteHost::PATTERN, SiteHost::suggest($slug), $slug);
        }
    }

    #[Test]
    public function фон_принимается_только_из_хранилища_сайтов(): void
    {
        $this->assertSame('sites/5/abc.jpg', SiteTheme::normalize(['hero_image' => 'sites/5/abc.jpg'])['hero_image']);

        foreach (['../../.env', 'https://evil.test/x.jpg', 'companies/5/a.jpg', 'sites/5/../x.jpg'] as $bad) {
            $this->assertNull(SiteTheme::normalize(['hero_image' => $bad])['hero_image'], $bad);
        }
    }

    /** Акцент в цвет фона на «Ярком» шаблоне не прячет кнопку. */
    #[Test]
    public function кнопка_на_фирменном_фоне_остаётся_видна(): void
    {
        $vars = SiteTheme::variables(SiteTheme::normalize(['primary' => '#7a4acb', 'accent' => '#7a4acb']));

        $this->assertGreaterThanOrEqual(1.6, SiteTheme::contrast($vars['--ms-hero-cta'], '#7a4acb'));
    }
}
