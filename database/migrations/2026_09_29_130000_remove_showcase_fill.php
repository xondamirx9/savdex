<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;

/**
 * Убрать «наполнение витрины» (ShowcaseSeeder) с живого сайта.
 *
 * Сидер на каждом деплое дописывал настоящим компаниям с пустым
 * профилем описание, собранное из их данных, а объявлениям без фото —
 * нарисованные картинки товара. Сами компании этого не писали и не
 * загружали. Теперь сидер на деплое не запускается (SEED_SHOWCASE
 * по умолчанию false), а сделанное им убирается.
 *
 * Узнаётся дословно: картинки — по пути listings/<id>/showcase-N.svg,
 * описания — по фразам сидера в начале и в конце. Описание, которое
 * компания переписала своими словами, этим фразам уже не отвечает
 * и остаётся.
 */
return new class extends Migration
{
    private const ENDING = 'Свяжитесь с нами через площадку SavdEx — ответим на запрос в рабочее время.';

    private const MIDDLES = [
        'Работаем с оптовыми заказами по договору поставки, отгружаем по Узбекистану и в соседние страны. Условия оплаты и доставки обсуждаются под объём.',
        'Закупаем оптовыми партиями на постоянной основе; рассматриваем предложения поставщиков по прайс-листу и под заказ.',
    ];

    private const OPENINGS = [
        'Производственная компания из ',
        'Дистрибьютор и оптовый поставщик из ',
        'Торговая компания из ',
        'Компания из ',
    ];

    public function up(): void
    {
        DB::table('companies')
            ->where('description', 'like', '%'.self::ENDING)
            ->where(fn ($q) => collect(self::OPENINGS)->each(fn (string $o) => $q->orWhere('description', 'like', $o.'%')))
            ->where(fn ($q) => collect(self::MIDDLES)->each(fn (string $m) => $q->orWhere('description', 'like', '%'.$m.'%')))
            ->update(['description' => null, 'updated_at' => now()]);

        $images = DB::table('listing_images')->where('path', 'like', 'listings/%/showcase-%');

        foreach ($images->pluck('path') as $path) {
            rescue(fn () => Storage::disk('public')->delete($path), report: false);
        }

        $images->delete();
    }

    public function down(): void
    {
        // Возвращать сгенерированное незачем
    }
};
