<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * «Запросы (RFQ)» на главной становятся просто «Запросами».
 *
 * RFQ — термин из закупочного жаргона: в скобках он ничего не
 * объяснял тому, кто его не знает, а тому, кто знает, был не нужен.
 * Решение заказчика.
 *
 * Заголовок секции лежит в landing_blocks: его правят в админке,
 * и файл database/data/landing.php читает только миграция, которая
 * уже выполнена. Поэтому правка идёт отдельной миграцией, а не
 * правкой файла — иначе на работающем стенде осталось бы старое.
 *
 * Переписываем только те строки, что совпадают с прежним текстом:
 * заголовок, переписанный в админке, — осознанная правка, и
 * возвращать его к значению из кода незачем.
 */
return new class extends Migration
{
    /** Язык => было => стало. Русский лежит в основных столбцах. */
    private const HEADINGS = [
        'ru' => ['Запросы (RFQ)', 'Запросы'],
        'uz' => ['So‘rovlar (RFQ)', 'So‘rovlar'],
        'en' => ['Requests (RFQ)', 'Requests'],
        'zh' => ['采购需求 (RFQ)', '采购需求'],
        'tr' => ['Talepler (RFQ)', 'Talepler'],
    ];

    public function up(): void
    {
        $this->rename(fromOld: true);
    }

    public function down(): void
    {
        $this->rename(fromOld: false);
    }

    private function rename(bool $fromOld): void
    {
        $block = DB::table('landing_blocks')->where('key', 'requests')->first();

        if ($block === null) {
            return;
        }

        [$oldRu, $newRu] = self::HEADINGS['ru'];
        [$from, $to] = $fromOld ? [$oldRu, $newRu] : [$newRu, $oldRu];

        $update = [];

        if (($block->heading ?? null) === $from) {
            $update['heading'] = $to;
        }

        if (($block->name ?? null) === $from) {
            $update['name'] = $to;
        }

        /** @var array<string, string> $i18n */
        $i18n = json_decode((string) ($block->heading_i18n ?? '{}'), true) ?: [];
        $changed = false;

        foreach (self::HEADINGS as $locale => [$old, $new]) {
            if ($locale === 'ru') {
                continue;
            }

            [$was, $becomes] = $fromOld ? [$old, $new] : [$new, $old];

            if (($i18n[$locale] ?? null) === $was) {
                $i18n[$locale] = $becomes;
                $changed = true;
            }
        }

        if ($changed) {
            $update['heading_i18n'] = json_encode($i18n, JSON_UNESCAPED_UNICODE);
        }

        if ($update !== []) {
            DB::table('landing_blocks')->where('key', 'requests')->update($update);
        }
    }
};
