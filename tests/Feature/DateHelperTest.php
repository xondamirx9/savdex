<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Support\DateHelper;
use Illuminate\Support\Carbon;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/** Даты словами на языках сайта (App\Support\DateHelper). */
class DateHelperTest extends TestCase
{
    #[Test]
    public function месяц_с_годом_на_языке_страницы(): void
    {
        $date = Carbon::create(2019, 6, 1, 12);

        // Месяц без числа Carbon берёт из «самостоятельных» названий,
        // а при общем языке сайта недостающие брал из запасного
        // русского: на английской визитке было «на площадке с июнь 2019»
        $expected = ['ru' => 'июня 2019', 'en' => 'June 2019', 'tr' => 'Haziran 2019', 'zh' => '六月 2019'];

        foreach ($expected as $locale => $text) {
            app()->setLocale($locale);

            $this->assertSame($text, DateHelper::monthYear($date), $locale);
        }
    }
}
