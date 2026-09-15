<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Category;
use App\Models\CategoryTranslation;
use App\Models\City;
use App\Models\CityTranslation;
use App\Models\Company;
use App\Models\Country;
use App\Models\CountryTranslation;

/**
 * Поиск записей справочников по тому, что написал человек.
 *
 * Менеджеру неоткуда взять id категории или города, поэтому в таблицах
 * стоят названия — на том языке, на котором менеджер работает, и в том
 * написании, в каком запомнил. Сравнение идёт по ImportLanguage:
 * регистр, «ё», неразрывные пробелы и апострофы приводятся к одному
 * виду, иначе «Черные металлы» не находят «Чёрные металлы».
 *
 * Не найдено — null. Что делать дальше, решает вызывающий: тендеру
 * без категории на витрине делать нечего, а объявление без города
 * живёт спокойно.
 */
final class CatalogLookup
{
    /**
     * Категория по slug, названию на любом языке или пути
     * «Раздел → Подраздел» — так название копируют из админки.
     *
     * Сравнение в PHP, а не lower() в SQL: lower() SQLite не трогает
     * кириллицу, и «Стройматериалы» не нашлись бы по «стройматериалы».
     */
    public static function categoryId(?string $value): ?int
    {
        $path = self::path($value);

        if ($path === []) {
            return null;
        }

        $last = array_key_last($path);
        $name = $path[$last];
        $parentName = $last > 0 ? $path[$last - 1] : null;

        $categories = Category::query()->with('translations')->get();
        $matches = $categories->filter(fn (Category $c): bool => self::isNamedCategory($c, $name));

        // Подкатегорий «Другое» столько же, сколько разделов: без
        // уточнения из пути объявление попало бы в первый попавшийся
        if ($matches->count() > 1 && $parentName !== null) {
            $narrowed = $matches->filter(function (Category $c) use ($categories, $parentName): bool {
                $parent = $categories->firstWhere('id', $c->parent_id);

                return $parent !== null && self::isNamedCategory($parent, $parentName);
            });

            if ($narrowed->isNotEmpty()) {
                $matches = $narrowed;
            }
        }

        return $matches->first()?->id;
    }

    /** Страна по коду ISO («uz») или названию на любом языке. */
    public static function countryId(?string $value): ?int
    {
        $needle = ImportLanguage::normalize($value);

        if ($needle === '') {
            return null;
        }

        $byCode = Country::query()->where('code', $needle)->value('id');

        if ($byCode !== null) {
            return (int) $byCode;
        }

        $match = CountryTranslation::query()
            ->get(['country_id', 'name'])
            ->first(fn (CountryTranslation $t): bool => ImportLanguage::normalize($t->name) === $needle);

        return $match === null ? null : (int) $match->country_id;
    }

    /**
     * Город по slug или названию на любом языке.
     *
     * «г. Ташкент» и «Toshkent sh.» — тот же город: приписка вида
     * города в таблицах встречается чаще, чем чистое название.
     */
    public static function cityId(?string $value): ?int
    {
        $needle = self::withoutCityPrefix(ImportLanguage::normalize($value));

        if ($needle === '') {
            return null;
        }

        $bySlug = City::query()->where('slug', $needle)->value('id');

        if ($bySlug !== null) {
            return (int) $bySlug;
        }

        $match = CityTranslation::query()
            ->get(['city_id', 'name'])
            ->first(fn (CityTranslation $t): bool => self::withoutCityPrefix(ImportLanguage::normalize($t->name)) === $needle);

        return $match === null ? null : (int) $match->city_id;
    }

    /**
     * Компания по ИНН или названию.
     *
     * ИНН проверяется первым: «ООО Стройбаза» и «ООО «Стройбаза»» —
     * одна компания, а два разных ИНН означают два разных юрлица
     * даже при одинаковом названии.
     */
    public static function companyId(?string $value): ?int
    {
        $raw = trim((string) $value);
        $needle = ImportLanguage::normalize($raw);

        if ($needle === '') {
            return null;
        }

        if (preg_match('/^\d{6,20}$/', $raw) === 1) {
            $byTin = Company::query()->where('tin', $raw)->value('id');

            if ($byTin !== null) {
                return (int) $byTin;
            }
        }

        $match = Company::query()
            ->get(['id', 'name', 'legal_name', 'tin'])
            ->first(fn (Company $c): bool => ImportLanguage::normalize($c->name) === $needle
                || ImportLanguage::normalize((string) $c->legal_name) === $needle
                || (string) $c->tin === $raw);

        return $match?->id;
    }

    private static function isNamedCategory(Category $category, string $needle): bool
    {
        if (ImportLanguage::normalize($category->slug) === $needle) {
            return true;
        }

        return $category->translations
            ->contains(fn (CategoryTranslation $t): bool => ImportLanguage::normalize($t->name) === $needle);
    }

    /**
     * Значение ячейки — путь из нормализованных частей.
     *
     * «Стройматериалы → Цемент и бетон», «Стройматериалы / Цемент и
     * бетон» и просто «Цемент и бетон» приводятся к одному виду.
     *
     * @return list<string>
     */
    private static function path(?string $value): array
    {
        $parts = preg_split('#\s*(?:→|->|>|/|\\\\|\|)\s*#u', (string) $value) ?: [];
        $parts = array_map(ImportLanguage::normalize(...), $parts);

        return array_values(array_filter($parts, fn (string $part): bool => $part !== ''));
    }

    /** «г. ташкент», «ташкент г.», «toshkent sh.» → «ташкент». */
    private static function withoutCityPrefix(string $value): string
    {
        $value = (string) preg_replace('/^(?:г|гор|город|sh|shahri|shahar)\.?\s+/u', '', $value);
        $value = (string) preg_replace('/\s+(?:г|гор|город|sh|shahri|shahar)\.?$/u', '', $value);

        return trim($value);
    }
}
