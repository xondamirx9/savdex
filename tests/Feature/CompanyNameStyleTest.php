<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Support\CompanyNameStyle;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Названия из госреестра пишутся капсом и на витрине выглядят криком.
 * Капс переводится в «Каждое Слово С Заглавной», смешанный регистр —
 * авторское написание — не трогается.
 */
class CompanyNameStyleTest extends TestCase
{
    #[Test]
    public function капс_очеловечивается_а_смешанный_регистр_не_трогается(): void
    {
        $this->assertSame('Toshkent Matras Lyuks', CompanyNameStyle::humanize('TOSHKENT MATRAS LYUKS'));
        $this->assertSame('Русский Лес', CompanyNameStyle::humanize('РУССКИЙ ЛЕС'));
        $this->assertSame('Zmatras', CompanyNameStyle::humanize('ZMATRAS'));

        // Юридической аббревиатуре капс положен
        $this->assertSame('ООО Ромашка', CompanyNameStyle::humanize('ООО РОМАШКА'));

        // Авторское написание — не наше дело
        $this->assertSame('EverForm', CompanyNameStyle::humanize('EverForm'));
        $this->assertSame('ооо ромашка', CompanyNameStyle::humanize('ооо ромашка'));
    }

    #[Test]
    public function вольная_запись_типа_приводится_к_ключу_справочника(): void
    {
        $this->assertSame('trader', CompanyNameStyle::typeKey('trading'));
        $this->assertSame('trader', CompanyNameStyle::typeKey('Торговая'));
        $this->assertSame('manufacturer', CompanyNameStyle::typeKey('manufacturer'));
        $this->assertSame('manufacturer', CompanyNameStyle::typeKey('Производитель'));
        $this->assertNull(CompanyNameStyle::typeKey(''));
    }
}
