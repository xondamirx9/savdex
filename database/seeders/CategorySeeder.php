<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\Category;
use App\Models\CategoryField;
use Illuminate\Database\Seeder;

/**
 * Категории каталога с переводами и полями.
 *
 * Пять языков заданы сразу: подставлять русское название вместо
 * отсутствующего перевода можно, но тогда никогда не видно, что
 * перевода нет, и он не появляется.
 */
class CategorySeeder extends Seeder
{
    /**
     * Дерево категорий. Названия — [ru, uz, en, zh, tr].
     *
     * В каждом разделе последней стоит подкатегория «Другое», а в конце
     * списка — одноимённый раздел: у любого товара должно быть место.
     */
    private const TREE = [
        ['stroymaterialy', 'package', ['Стройматериалы', 'Qurilish mollari', 'Construction materials', '建筑材料', 'İnşaat malzemeleri'], [
            ['cement-beton', ['Цемент и бетон', 'Sement va beton', 'Cement and concrete', '水泥和混凝土', 'Çimento ve beton']],
            ['metalloprokat', ['Металлопрокат', 'Metall prokat', 'Rolled metal', '轧制金属', 'Haddelenmiş metal']],
            ['krovlya-fasad', ['Кровля и фасад', 'Tom va fasad', 'Roofing and facade', '屋顶和外墙', 'Çatı ve cephe']],
            ['kirpich-blok', ['Кирпич и блоки', 'Gʻisht va bloklar', 'Bricks and blocks', '砖和砌块', 'Tuğla ve blok']],
            ['stroymaterialy-drugoe', ['Другое', 'Boshqa', 'Other', '其他', 'Diğer']],
        ]],
        ['tekstil', 'shirt', ['Текстиль и одежда', 'Toʻqimachilik va kiyim', 'Textile and clothing', '纺织品和服装', 'Tekstil ve giyim'], [
            ['pryazha-tkani', ['Пряжа и ткани', 'Ip va matolar', 'Yarn and fabrics', '纱线和织物', 'İplik ve kumaş']],
            ['gotovaya-odezhda', ['Готовая одежда', 'Tayyor kiyim', 'Ready-made clothing', '成衣', 'Hazır giyim']],
            ['tekstil-drugoe', ['Другое', 'Boshqa', 'Other', '其他', 'Diğer']],
        ]],
        ['metally', 'layers', ['Металлы', 'Metallar', 'Metals', '金属', 'Metaller'], [
            ['chernye-metally', ['Чёрные металлы', 'Qora metallar', 'Ferrous metals', '黑色金属', 'Demir metaller']],
            ['cvetnye-metally', ['Цветные металлы', 'Rangli metallar', 'Non-ferrous metals', '有色金属', 'Demir dışı metaller']],
            ['metally-drugoe', ['Другое', 'Boshqa', 'Other', '其他', 'Diğer']],
        ]],
        ['produkty', 'wheat', ['Продукты питания', 'Oziq-ovqat', 'Food products', '食品', 'Gıda ürünleri'], [
            ['zerno-muka', ['Зерно и мука', 'Don va un', 'Grain and flour', '谷物和面粉', 'Tahıl ve un']],
            ['sukhofrukty', ['Сухофрукты', 'Quruq mevalar', 'Dried fruits', '干果', 'Kuru meyveler']],
            ['produkty-drugoe', ['Другое', 'Boshqa', 'Other', '其他', 'Diğer']],
        ]],
        ['upakovka', 'box', ['Упаковка', 'Qadoqlash', 'Packaging', '包装', 'Ambalaj'], [
            ['poddony-tara', ['Поддоны и тара', 'Palletlar va idishlar', 'Pallets and containers', '托盘和容器', 'Palet ve kaplar']],
            ['upakovka-drugoe', ['Другое', 'Boshqa', 'Other', '其他', 'Diğer']],
        ]],
        ['oborudovanie', 'settings', ['Оборудование', 'Uskunalar', 'Equipment', '设备', 'Ekipman'], [
            ['stanki', ['Станки', 'Dastgohlar', 'Machine tools', '机床', 'Takım tezgahları']],
            ['oborudovanie-drugoe', ['Другое', 'Boshqa', 'Other', '其他', 'Diğer']],
        ]],

        ['uslugi', 'briefcase', ['Услуги', 'Xizmatlar', 'Services', '服务', 'Hizmetler'], [
            ['hr-uslugi', ['Эйчар и подбор персонала', 'HR va xodimlar tanlash', 'HR and recruiting', '人力资源与招聘', 'İK ve işe alım']],
            ['finansy-buhgalteriya', ['Финансы и бухгалтерия', 'Moliya va buxgalteriya', 'Finance and accounting', '财务与会计', 'Finans ve muhasebe']],
            ['uslugi-drugoe', ['Другое', 'Boshqa', 'Other', '其他', 'Diğer']],
        ]],

        /*
         * Раздел-приют для товара, которому не нашлось рубрики: без него
         * продавец бросает мастер на первом же шаге. Стоит последним —
         * «Другое» выбирают, когда просмотрели остальное.
         */
        ['drugoe', 'other', ['Другое', 'Boshqa', 'Other', '其他', 'Diğer'], [
            ['raznye-tovary', ['Разные товары', 'Turli tovarlar', 'Miscellaneous goods', '其他商品', 'Çeşitli ürünler']],
        ]],
    ];

    private const LOCALES = ['ru', 'uz', 'en', 'zh', 'tr'];

    /** Поля, специфичные для отдельных подкатегорий. */
    private const FIELDS = [
        'cement-beton' => [
            ['key' => 'mark', 'label' => 'Марка', 'options' => ['М300', 'М400', 'М500', 'М600']],
            ['key' => 'additive', 'label' => 'Добавка', 'options' => ['Д0', 'Д5', 'Д20']],
            ['key' => 'packing', 'label' => 'Фасовка', 'options' => ['Навалом', 'Мешки 50 кг', 'Биг-бэг 1 т']],
        ],
        'metalloprokat' => [
            ['key' => 'profile', 'label' => 'Профиль', 'options' => ['Арматура', 'Швеллер', 'Уголок', 'Лист', 'Труба']],
            ['key' => 'steel', 'label' => 'Марка стали', 'options' => ['Ст3', 'Ст5', '09Г2С']],
        ],
        'pryazha-tkani' => [
            ['key' => 'composition', 'label' => 'Состав', 'options' => ['100 % хлопок', 'Хлопок/ПЭ', 'Вискоза']],
            ['key' => 'density', 'label' => 'Плотность, г/м²', 'type' => 'number'],
        ],

        /*
         * Подкатегории «Другое» получают свободное текстовое поле:
         * готовой рубрики для товара нет, и продавец называет её сам.
         * Введённое видно на карточке объявления рядом с остальными
         * характеристиками.
         */
        'stroymaterialy-drugoe' => self::CUSTOM_CATEGORY_FIELD,
        'tekstil-drugoe' => self::CUSTOM_CATEGORY_FIELD,
        'metally-drugoe' => self::CUSTOM_CATEGORY_FIELD,
        'produkty-drugoe' => self::CUSTOM_CATEGORY_FIELD,
        'upakovka-drugoe' => self::CUSTOM_CATEGORY_FIELD,
        'oborudovanie-drugoe' => self::CUSTOM_CATEGORY_FIELD,
        'uslugi-drugoe' => self::CUSTOM_CATEGORY_FIELD,
        'raznye-tovary' => self::CUSTOM_CATEGORY_FIELD,
    ];

    /** Поле «назовите категорию сами» — одно на все подкатегории «Другое». */
    private const CUSTOM_CATEGORY_FIELD = [
        ['key' => 'custom_category', 'label' => 'Категория товара', 'type' => 'text'],
    ];

    public function run(): void
    {
        foreach (self::TREE as $sort => [$slug, $icon, $names, $children]) {
            $parent = $this->make($slug, $icon, $names, $sort, null);

            foreach ($children as $childSort => [$childSlug, $childNames]) {
                $child = $this->make($childSlug, null, $childNames, $childSort, $parent->id);
                $this->attachFields($child);
            }
        }
    }

    /** @param list<string> $names */
    private function make(string $slug, ?string $icon, array $names, int $sort, ?int $parentId): Category
    {
        $category = Category::updateOrCreate(
            ['slug' => $slug],
            ['parent_id' => $parentId, 'icon' => $icon, 'sort' => $sort, 'is_active' => true],
        );

        foreach (self::LOCALES as $i => $locale) {
            $category->translations()->updateOrCreate(
                ['locale' => $locale],
                ['name' => $names[$i]],
            );
        }

        return $category;
    }

    private function attachFields(Category $category): void
    {
        foreach (self::FIELDS[$category->slug] ?? [] as $sort => $field) {
            CategoryField::updateOrCreate(
                ['category_id' => $category->id, 'key' => $field['key']],
                [
                    'label' => $field['label'],
                    'type' => $field['type'] ?? 'select',
                    'options' => $field['options'] ?? null,
                    'sort' => $sort,
                ],
            );
        }
    }
}
