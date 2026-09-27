<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Страницы «О компании», «Помощь», «Инструкция» и «Правила» переезжают
 * из словарей в базу — их правят в админке.
 *
 * До сих пор сайт брал эти тексты из lang/<язык>/ui.php, а таблицу
 * pages не читал вовсе: правка в разделе «Страницы и FAQ» никуда не
 * доходила. Теперь у текста есть поля под каждый язык (*_i18n,
 * {"uz": "...", "en": "..."}; русский — в основных столбцах). Пустой
 * язык сайт показывает машинным переводом русского текста.
 *
 * Тексты переносятся такими, какими их показывал сайт
 * (database/data/pages.php), — поверх того, что туда когда-то положил
 * CmsSeeder: его тексты нигде не показывались и успели устареть.
 */
return new class extends Migration
{
    private const LOCALES = ['uz', 'en', 'zh', 'tr'];

    public function up(): void
    {
        Schema::table('pages', function (Blueprint $table): void {
            $table->json('title_i18n')->nullable();
            $table->json('excerpt_i18n')->nullable();
            $table->json('body_i18n')->nullable();
        });

        Schema::table('faq_items', function (Blueprint $table): void {
            $table->json('question_i18n')->nullable();
            $table->json('answer_i18n')->nullable();
        });

        $data = require database_path('data/pages.php');
        $now = now();

        foreach (array_keys($data['pages']) as $sort => $key) {
            $texts = $data['pages'][$key];
            $row = [
                'title' => $texts['ru']['title'],
                'excerpt' => $texts['ru']['excerpt'] ?: null,
                'body' => $texts['ru']['body'] ?: null,
                'title_i18n' => $this->i18n($texts, 'title'),
                'excerpt_i18n' => $this->i18n($texts, 'excerpt'),
                'body_i18n' => $this->i18n($texts, 'body'),
                'updated_at' => $now,
            ];

            if (DB::table('pages')->where('key', $key)->exists()) {
                DB::table('pages')->where('key', $key)->update($row);
            } else {
                DB::table('pages')->insert($row + [
                    'key' => $key,
                    'slug' => $key,
                    'is_published' => true,
                    'sort' => $sort,
                    'created_at' => $now,
                ]);
            }
        }

        // Вопросы помощи — только если их ещё никто не завёл
        $help = DB::table('pages')->where('key', 'help')->value('id');

        if (DB::table('faq_items')->where('page_id', $help)->exists()) {
            return;
        }

        foreach ($data['faq'] as $sort => $texts) {
            DB::table('faq_items')->insert([
                'page_id' => $help,
                'question' => $texts['ru']['question'],
                'answer' => $texts['ru']['answer'],
                'question_i18n' => $this->i18n($texts, 'question'),
                'answer_i18n' => $this->i18n($texts, 'answer'),
                'sort' => $sort,
                'is_published' => true,
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        }
    }

    public function down(): void
    {
        Schema::table('pages', function (Blueprint $table): void {
            $table->dropColumn(['title_i18n', 'excerpt_i18n', 'body_i18n']);
        });

        Schema::table('faq_items', function (Blueprint $table): void {
            $table->dropColumn(['question_i18n', 'answer_i18n']);
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
