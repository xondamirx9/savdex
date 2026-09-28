<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Category;

/**
 * Детали товара: вес, размеры, цвет, материал — блок «Информация
 * о товаре» на шаге «Товар и цена» мастера объявления.
 *
 * Набор полей зависит от категории: у металлопроката спрашивают
 * толщину, диаметр и марку стали, у ткани — состав и плотность,
 * у продуктов — срок годности и хранение, у услуг блока нет вовсе.
 * Все поля необязательные: продавец, который не знает деталей,
 * пропускает блок, и объявление публикуется как раньше.
 *
 * Наборы описаны здесь, а не в таблице полей категорий: разделы
 * правятся в админке на Python, и новая категория без описания
 * получает общий набор для товаров, а не пустой блок.
 *
 * Значения хранятся в характеристиках объявления (listing_attributes)
 * с ключами spec_*: так они не пересекаются с полями категорий
 * (марка цемента, профиль) и выводятся на карточке тем же списком.
 * Формат значения — код, а не подпись, чтобы карточка показывалась
 * на языке посетителя:
 *
 *   мера      «25 kg»          число и код единицы
 *   размеры   «120x60x75 cm»   три числа (пустые допустимы) и единица
 *   выбор     «black»          код варианта либо свой текст («Другое»)
 *   текст     «ГОСТ 5781-82»   как ввели
 */
class ProductSpecs
{
    /** Префикс ключа характеристики. */
    public const PREFIX = 'spec_';

    /** Предел длины значения: деталь, а не описание. */
    public const MAX_LENGTH = 120;

    /**
     * Поля: вид и допустимые единицы или варианты.
     *
     * @var array<string, array{type: string, units?: list<string>, options?: string, custom?: bool}>
     */
    private const FIELDS = [
        'weight' => ['type' => 'measure', 'units' => ['kg', 't', 'g']],
        'dimensions' => ['type' => 'dims', 'units' => ['cm', 'mm', 'm']],
        'length' => ['type' => 'measure', 'units' => ['mm', 'm']],
        'thickness' => ['type' => 'measure', 'units' => ['mm']],
        'diameter' => ['type' => 'measure', 'units' => ['mm']],
        'width' => ['type' => 'measure', 'units' => ['cm', 'm']],
        'density' => ['type' => 'measure', 'units' => ['gsm']],
        'capacity' => ['type' => 'measure', 'units' => ['l']],
        'load' => ['type' => 'measure', 'units' => ['kg', 't']],
        'power' => ['type' => 'measure', 'units' => ['kw']],
        'shelf_life' => ['type' => 'measure', 'units' => ['months', 'days', 'years']],
        'warranty' => ['type' => 'measure', 'units' => ['months', 'years']],
        'year' => ['type' => 'number'],
        'color' => ['type' => 'select', 'options' => 'color', 'custom' => true],
        'material' => ['type' => 'select', 'options' => 'material', 'custom' => true],
        'composition' => ['type' => 'select', 'options' => 'material', 'custom' => true],
        'coating' => ['type' => 'select', 'options' => 'coating', 'custom' => true],
        'packaging' => ['type' => 'select', 'options' => 'packaging', 'custom' => true],
        'storage' => ['type' => 'select', 'options' => 'storage', 'custom' => true],
        'condition' => ['type' => 'select', 'options' => 'condition'],
        'voltage' => ['type' => 'select', 'options' => 'voltage', 'custom' => true],
        'grade' => ['type' => 'text'],
        'sizes' => ['type' => 'text'],
        'brand' => ['type' => 'text'],
        'origin' => ['type' => 'text'],
    ];

    /**
     * Наборы полей по разделу (верхней категории), в порядке важности.
     * Пустой набор — у раздела нет физического товара (услуги).
     *
     * @var array<string, list<string>>
     */
    private const SETS = [
        'stroymaterialy' => ['weight', 'dimensions', 'material', 'color', 'grade', 'packaging', 'brand', 'origin'],
        'metally' => ['material', 'grade', 'weight', 'length', 'thickness', 'diameter', 'coating', 'origin'],
        'tekstil' => ['composition', 'color', 'density', 'width', 'sizes', 'weight', 'brand', 'origin'],
        'produkty' => ['weight', 'packaging', 'shelf_life', 'storage', 'grade', 'brand', 'origin'],
        'upakovka' => ['material', 'dimensions', 'capacity', 'load', 'color', 'weight', 'origin'],
        'oborudovanie' => ['condition', 'power', 'voltage', 'weight', 'dimensions', 'year', 'warranty', 'brand', 'origin'],
        'mebel' => ['dimensions', 'material', 'color', 'weight', 'warranty', 'brand', 'origin'],
        'vystavki' => [],
        'logistika' => [],
        'uslugi' => [],
    ];

    /**
     * Подкатегории, товар которых ближе к другому разделу: металлопрокат
     * лежит в стройматериалах, но описывается как металл.
     *
     * @var array<string, list<string>>
     */
    private const CHILD_SETS = [
        'metalloprokat' => ['material', 'grade', 'weight', 'length', 'thickness', 'diameter', 'coating', 'origin'],
        'krovlya-fasad' => ['material', 'dimensions', 'thickness', 'color', 'coating', 'weight', 'brand', 'origin'],
        'cement-beton' => ['weight', 'packaging', 'grade', 'brand', 'origin'],
        'kirpich-blok' => ['dimensions', 'material', 'weight', 'color', 'grade', 'brand', 'origin'],
        'gotovaya-odezhda' => ['composition', 'color', 'sizes', 'brand', 'origin'],
        'zerno-muka' => ['weight', 'packaging', 'grade', 'shelf_life', 'storage', 'origin'],
        'poddony-tara' => ['material', 'dimensions', 'load', 'weight', 'origin'],
    ];

    /** Набор для товара без описанного раздела. */
    private const DEFAULT_SET = ['weight', 'dimensions', 'color', 'material', 'brand', 'origin'];

    /**
     * Варианты материала — по разделу: у ткани нет бетона, у металла — хлопка.
     *
     * @var array<string, list<string>>
     */
    private const MATERIALS = [
        'stroymaterialy' => ['concrete', 'ceramic', 'stone', 'gypsum', 'wood', 'metal', 'steel', 'plastic', 'glass'],
        'metally' => ['steel', 'stainless', 'cast_iron', 'aluminium', 'copper', 'brass', 'bronze', 'zinc', 'lead', 'titanium'],
        'tekstil' => ['cotton', 'polyester', 'cotton_poly', 'viscose', 'wool', 'silk', 'linen', 'nylon', 'leather'],
        'upakovka' => ['cardboard', 'paper', 'polyethylene', 'plastic', 'wood', 'glass', 'metal'],
        'oborudovanie' => ['steel', 'stainless', 'cast_iron', 'aluminium', 'plastic'],
        'mebel' => ['solid_wood', 'mdf', 'chipboard', 'metal', 'plastic', 'glass', 'fabric', 'leather', 'eco_leather'],
        'metalloprokat' => ['steel', 'stainless', 'cast_iron', 'aluminium', 'copper', 'brass', 'zinc'],
        'krovlya-fasad' => ['steel', 'aluminium', 'ceramic', 'concrete', 'plastic', 'glass', 'wood'],
        'poddony-tara' => ['wood', 'plastic', 'metal', 'cardboard'],
    ];

    private const DEFAULT_MATERIALS = ['metal', 'wood', 'plastic', 'glass', 'fabric', 'paper', 'ceramic', 'rubber'];

    /** Ткань описывается составом из текстильных материалов. */
    private const COMPOSITION = ['cotton', 'polyester', 'cotton_poly', 'viscose', 'wool', 'silk', 'linen', 'nylon'];

    /**
     * Поля для формы — на языке сайта.
     *
     * @return list<array{key: string, label: string, type: string, units: list<array{value: string, label: string}>, options: list<array{value: string, label: string}>, custom: bool}>
     */
    public static function form(?string $parentSlug, ?string $childSlug): array
    {
        return array_map(
            fn (string $field): array => self::describe($field, $parentSlug, $childSlug),
            self::setFor($parentSlug, $childSlug),
        );
    }

    /** Поля категории объявления — для формы мастера. */
    public static function forCategory(?Category $category): array
    {
        if ($category === null) {
            return [];
        }

        $parent = $category->parent_id !== null ? $category->parent : $category;

        return self::form($parent?->slug, $category->parent_id !== null ? $category->slug : null);
    }

    /** Ключ характеристики — деталь товара. */
    public static function owns(string $key): bool
    {
        return str_starts_with($key, self::PREFIX) && isset(self::FIELDS[substr($key, strlen(self::PREFIX))]);
    }

    /**
     * Проверить значение перед записью. null — значение не годится
     * и сохраняться не должно (чужой ключ, мусор, слишком длинно);
     * пустая строка — поле очищено.
     */
    public static function clean(string $key, mixed $value): ?string
    {
        if (! self::owns($key)) {
            return null;
        }

        // Пустое поле приходит как null: Laravel превращает пустые
        // строки запроса в null — это очистка, а не мусор
        if ($value === null) {
            return '';
        }

        if (! (is_string($value) || is_int($value) || is_float($value))) {
            return null;
        }

        $value = trim(preg_replace('/\s+/u', ' ', (string) $value) ?? '');

        if ($value === '') {
            return '';
        }

        if (mb_strlen($value) > self::MAX_LENGTH) {
            return null;
        }

        $spec = self::FIELDS[substr($key, strlen(self::PREFIX))];

        return match ($spec['type']) {
            'measure' => self::cleanMeasure($value, $spec['units'] ?? []),
            'dims' => self::cleanDims($value, $spec['units'] ?? []),
            'number' => preg_match('/^\d{1,6}$/', $value) === 1 ? $value : null,
            default => strip_tags($value),
        };
    }

    /**
     * Строка для карточки товара: подпись и значение на языке посетителя.
     *
     * @return array{key: string, value: string}|null
     */
    public static function present(string $key, string $value): ?array
    {
        if (! self::owns($key) || trim($value) === '') {
            return null;
        }

        $field = substr($key, strlen(self::PREFIX));
        $spec = self::FIELDS[$field];

        return [
            'key' => __('specs.fields.'.$field),
            'value' => match ($spec['type']) {
                'measure' => self::presentMeasure($value),
                'dims' => self::presentDims($value),
                'select' => self::presentOption($spec['options'] ?? '', $value),
                default => (string) ContentTranslation::text($value),
            },
        ];
    }

    /** @return list<string> */
    private static function setFor(?string $parentSlug, ?string $childSlug): array
    {
        if ($childSlug !== null && isset(self::CHILD_SETS[$childSlug])) {
            return self::CHILD_SETS[$childSlug];
        }

        // Подкатегория «Другое» в разделе услуг — тоже услуга:
        // решает раздел, а не название подкатегории
        return $parentSlug !== null && array_key_exists($parentSlug, self::SETS)
            ? self::SETS[$parentSlug]
            : self::DEFAULT_SET;
    }

    /** @return array<string, mixed> */
    private static function describe(string $field, ?string $parentSlug, ?string $childSlug): array
    {
        $spec = self::FIELDS[$field];

        $options = match ($spec['options'] ?? null) {
            null => [],
            'material' => $field === 'composition'
                ? self::COMPOSITION
                : (self::MATERIALS[$childSlug ?? ''] ?? self::MATERIALS[$parentSlug ?? ''] ?? self::DEFAULT_MATERIALS),
            default => array_keys((array) trans('specs.options.'.$spec['options'], locale: 'ru')),
        };

        return [
            'key' => self::PREFIX.$field,
            'label' => __('specs.fields.'.$field),
            'type' => $spec['type'],
            'units' => array_map(
                fn (string $u): array => ['value' => $u, 'label' => __('specs.units.'.$u)],
                $spec['units'] ?? [],
            ),
            'options' => array_map(
                fn (string $o): array => ['value' => $o, 'label' => __('specs.options.'.$spec['options'].'.'.$o)],
                $options,
            ),
            'custom' => (bool) ($spec['custom'] ?? false),
        ];
    }

    /** @param list<string> $units */
    private static function cleanMeasure(string $value, array $units): ?string
    {
        if (preg_match('/^(\d{1,9}(?:[.,]\d{1,3})?) ([a-z]+)$/', $value, $m) !== 1 || ! in_array($m[2], $units, true)) {
            return null;
        }

        return str_replace(',', '.', $m[1]).' '.$m[2];
    }

    /** @param list<string> $units */
    private static function cleanDims(string $value, array $units): ?string
    {
        $num = '(\d{0,6}(?:[.,]\d{1,2})?)';

        if (preg_match("/^{$num}x{$num}x{$num} ([a-z]+)$/", $value, $m) !== 1 || ! in_array($m[4], $units, true)) {
            return null;
        }

        // Хотя бы одно измерение: «x x см» — не размеры
        if ($m[1] === '' && $m[2] === '' && $m[3] === '') {
            return '';
        }

        return str_replace(',', '.', "{$m[1]}x{$m[2]}x{$m[3]} {$m[4]}");
    }

    private static function presentMeasure(string $value): string
    {
        [$number, $unit] = array_pad(explode(' ', $value, 2), 2, '');

        return trim($number.' '.self::unit($unit));
    }

    private static function presentDims(string $value): string
    {
        [$sizes, $unit] = array_pad(explode(' ', $value, 2), 2, '');

        $parts = array_map(fn (string $p): string => $p === '' ? '—' : $p, explode('x', $sizes));

        return implode(' × ', $parts).' '.self::unit($unit);
    }

    private static function presentOption(string $group, string $value): string
    {
        $key = 'specs.options.'.$group.'.'.$value;

        // Свой вариант («Другое») показывается как написан — с переводом
        // текста, как у остальных свободных полей
        return trans()->has($key) ? __($key) : (string) ContentTranslation::text($value);
    }

    private static function unit(string $code): string
    {
        return $code !== '' && trans()->has('specs.units.'.$code) ? __('specs.units.'.$code) : $code;
    }
}
