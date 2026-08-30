<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Company;
use Illuminate\Support\Facades\Storage;

/**
 * Эмблема компании: градиентная плашка с инициалами.
 *
 * Настоящие логотипы площадка использовать не может — авторское
 * право, — поэтому эмблема рисуется своя: минималистичный квадрат
 * со скруглением в фирменной манере сайта, цвет — по региону
 * компании, буквы — инициалы названия. Компании без определимого
 * региона получают стабильный цвет по названию: одна и та же
 * компания всегда одного цвета.
 *
 * Файл сохраняется обычным логотипом (logo_path) — показывается
 * везде, где показывался бы загруженный логотип, и заменяется им,
 * если настоящий когда-нибудь появится.
 */
class CompanyEmblem
{
    /**
     * Палитры регионов: [верх градиента, низ градиента].
     * Тона приглушённые — плашка стоит рядом с фирменным синим сайта.
     */
    private const PALETTES = [
        'tashkent' => ['#2563ab', '#123f74'],   // фирменный синий
        'fergana' => ['#b02a4c', '#701a34'],    // малиновый
        'samarkand' => ['#1d5f9e', '#0e3a66'],  // глубокий синий
        'bukhara' => ['#b07430', '#77471a'],    // бронза
        'karakalpak' => ['#5d7268', '#39493f'], // серо-зелёный
        'navoi' => ['#8f8434', '#5c541e'],      // оливковое золото
        'surkhandarya' => ['#b0472a', '#742c18'], // терракота
        'khorezm' => ['#2a8a84', '#175450'],    // бирюза
        'andijan' => ['#7952a8', '#4c3070'],    // фиолетовый
        'namangan' => ['#468a3c', '#2b5a24'],   // зелёный
        'kashkadarya' => ['#a8552a', '#6e3418'],
        'jizzakh' => ['#58748f', '#37485c'],
        'syrdarya' => ['#3f8a9e', '#255866'],
    ];

    /** Приметы региона в городе или адресе. */
    private const REGION_HINTS = [
        'ташкент' => 'tashkent', 'toshkent' => 'tashkent', 'tashkent' => 'tashkent',
        'фергана' => 'fergana', 'фергán' => 'fergana', 'farg' => 'fergana', 'коканд' => 'fergana', 'маргилан' => 'fergana',
        'самарканд' => 'samarkand', 'samarqand' => 'samarkand',
        'бухар' => 'bukhara', 'buxoro' => 'bukhara',
        'нукус' => 'karakalpak', 'каракалпак' => 'karakalpak',
        'навои' => 'navoi', 'navoiy' => 'navoi', 'зарафшан' => 'navoi',
        'термез' => 'surkhandarya', 'сурхандарь' => 'surkhandarya',
        'ургенч' => 'khorezm', 'хорезм' => 'khorezm', 'хива' => 'khorezm', 'urganch' => 'khorezm',
        'андижан' => 'andijan', 'andijon' => 'andijan',
        'наманган' => 'namangan', 'namangan' => 'namangan',
        'карши' => 'kashkadarya', 'кашкадарь' => 'kashkadarya', 'qarshi' => 'kashkadarya',
        'джизак' => 'jizzakh', 'jizzax' => 'jizzakh',
        'гулистан' => 'syrdarya', 'сырдарь' => 'syrdarya', 'guliston' => 'syrdarya',
    ];

    /** Сгенерировать эмблему и назначить её логотипом компании. */
    public static function assign(Company $company): void
    {
        $path = "companies/{$company->id}/emblem.svg";

        Storage::disk('public')->put($path, self::svg($company));

        $company->forceFill(['logo_path' => $path])->save();
    }

    public static function svg(Company $company): string
    {
        [$top, $bottom] = self::palette($company);
        $initials = htmlspecialchars($company->initials(), ENT_QUOTES);

        // Две буквы шире одной — кегль подбирается по длине
        $size = mb_strlen($initials) >= 2 ? 96 : 120;

        return <<<SVG
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{$top}"/>
      <stop offset="1" stop-color="{$bottom}"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="56" fill="url(#bg)"/>
  <text x="128" y="128" text-anchor="middle" dominant-baseline="central"
    font-family="Arial, Helvetica, sans-serif" font-weight="700"
    font-size="{$size}" fill="#ffffff" letter-spacing="1">{$initials}</text>
</svg>
SVG;
    }

    /** @return array{0: string, 1: string} */
    private static function palette(Company $company): array
    {
        $haystack = mb_strtolower(implode(' ', array_filter([
            $company->city?->name(),
            $company->address,
            $company->name,
        ])));

        foreach (self::REGION_HINTS as $hint => $region) {
            if (str_contains($haystack, $hint)) {
                return self::PALETTES[$region];
            }
        }

        // Регион неизвестен — стабильный цвет по названию: у одной
        // компании эмблема не меняется от генерации к генерации
        $keys = array_values(self::PALETTES);

        return $keys[crc32(mb_strtolower((string) $company->name)) % count($keys)];
    }
}
