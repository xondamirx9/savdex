<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Секция «Товары» на главной — между витриной VIP и запросами.
 *
 * Витрина VIP показывает только компании высшего тарифа и пуста,
 * пока таких нет: тогда между категориями и поставщиками товаров
 * не было вовсе. Новая лента — свежие предложения всех компаний.
 * Решение заказчика.
 *
 * Заголовок и видимость секции правятся в админке, как у остальных,
 * поэтому у неё своя строка в landing_blocks. Файл database/data/
 * landing.php читает только миграция, которая уже выполнена, — строка
 * заводится здесь.
 *
 * Порядок строк (sort) — порядок макета: раздел админки показывает
 * секции в нём. Он переписывается целиком, чтобы новая секция встала
 * после VIP, а не в конец списка.
 */
return new class extends Migration
{
    /** Секции главной в порядке макета — LandingBlock::KEYS на момент миграции. */
    private const ORDER = [
        'hero', 'stats', 'categories', 'vip', 'products', 'requests', 'suppliers',
        'how', 'reviews', 'faq', 'news', 'cta',
    ];

    /** Русский лежит в основных столбцах, остальные языки — в heading_i18n. */
    private const HEADINGS = [
        'ru' => 'Товары',
        'uz' => 'Mahsulotlar',
        'en' => 'Products',
        'zh' => '商品',
        'tr' => 'Ürünler',
    ];

    public function up(): void
    {
        if (! DB::table('landing_blocks')->where('key', 'products')->exists()) {
            $now = now();
            $i18n = self::HEADINGS;
            unset($i18n['ru']);

            DB::table('landing_blocks')->insert([
                'key' => 'products',
                'name' => self::HEADINGS['ru'],
                'heading' => self::HEADINGS['ru'],
                'heading_i18n' => json_encode($i18n, JSON_UNESCAPED_UNICODE),
                'is_visible' => true,
                'sort' => 0,
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        }

        $this->reorder(self::ORDER);
    }

    public function down(): void
    {
        DB::table('landing_blocks')->where('key', 'products')->delete();

        $this->reorder(array_values(array_diff(self::ORDER, ['products'])));
    }

    /** @param  list<string>  $keys */
    private function reorder(array $keys): void
    {
        foreach ($keys as $sort => $key) {
            DB::table('landing_blocks')->where('key', $key)->update(['sort' => $sort]);
        }
    }
};
