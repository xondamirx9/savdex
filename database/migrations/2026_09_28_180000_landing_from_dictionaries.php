<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Тексты главной страницы переезжают из словарей в базу — их правят
 * в админке (решение заказчика: тексты, вопросы и видимость секций;
 * порядок — как в макете).
 *
 * До сих пор главная брала тексты из lang/<язык>/ui.php, а таблицу
 * landing_blocks не читала: правка «Блоков главной» никуда не доходила.
 * Теперь блок — секция главной: у текста поля под каждый язык (*_i18n,
 * {"uz": "..."}; русский — в основных столбцах), пустой язык сайт
 * показывает машинным переводом. Пункты «Как это работает» и «Частых
 * вопросов» — в столбце body (название первой строкой, пояснение
 * следующей, пункты через пустую строку), у призыва в конце body —
 * подпись под кнопкой.
 *
 * Блоки roles, value и trust убираются: этих секций в макете больше
 * нет. Тексты переносятся такими, какими их показывал сайт
 * (database/data/landing.php), — поверх того, что туда когда-то положил
 * CmsSeeder: его тексты нигде не показывались.
 */
return new class extends Migration
{
    private const LOCALES = ['uz', 'en', 'zh', 'tr'];

    private const FIELDS = ['eyebrow', 'heading', 'subheading', 'button', 'body'];

    public function up(): void
    {
        Schema::table('landing_blocks', function (Blueprint $table): void {
            $table->json('eyebrow_i18n')->nullable();
            $table->json('heading_i18n')->nullable();
            $table->json('subheading_i18n')->nullable();
            $table->string('button')->nullable();
            $table->json('button_i18n')->nullable();
            $table->text('body')->nullable();
            $table->json('body_i18n')->nullable();
        });

        DB::table('landing_blocks')->whereIn('key', ['roles', 'value', 'trust'])->delete();

        $data = require database_path('data/landing.php');
        $now = now();

        foreach (array_keys($data) as $sort => $key) {
            $texts = $data[$key]['texts'];
            $row = ['name' => $data[$key]['name'], 'sort' => $sort, 'updated_at' => $now];

            foreach (self::FIELDS as $field) {
                $row[$field] = ($texts['ru'][$field] ?? '') ?: null;
                $row[$field.'_i18n'] = $this->i18n($texts, $field);
            }

            if (DB::table('landing_blocks')->where('key', $key)->exists()) {
                DB::table('landing_blocks')->where('key', $key)->update($row);
            } else {
                DB::table('landing_blocks')->insert($row + [
                    'key' => $key,
                    'is_visible' => true,
                    'created_at' => $now,
                ]);
            }
        }
    }

    public function down(): void
    {
        Schema::table('landing_blocks', function (Blueprint $table): void {
            $table->dropColumn([
                'eyebrow_i18n', 'heading_i18n', 'subheading_i18n',
                'button', 'button_i18n', 'body', 'body_i18n',
            ]);
        });
    }

    /** @param  array<string, array<string, string>>  $texts */
    private function i18n(array $texts, string $field): ?string
    {
        $values = [];

        foreach (self::LOCALES as $locale) {
            $value = trim($texts[$locale][$field] ?? '');

            if ($value !== '') {
                $values[$locale] = $value;
            }
        }

        return $values === [] ? null : json_encode($values, JSON_UNESCAPED_UNICODE);
    }
};
