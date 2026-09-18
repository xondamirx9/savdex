<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Переводы резюме на языки площадки.
 *
 * Резюме пишут по-русски или по-узбекски, а ищут людей и турецкие,
 * и китайские компании. Без перевода английская версия раздела
 * показывала русские должности — то есть не показывала ничего.
 *
 * Хранится тем же способом, что переводы объявлений: оригинал
 * в колонке, переводы рядом в json по коду языка. Места работы
 * переводятся списком в том же порядке, что и оригинал.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('resumes', function (Blueprint $table): void {
            $table->json('title_i18n')->nullable()->after('title');
            $table->json('about_i18n')->nullable()->after('about');
            $table->json('jobs_i18n')->nullable()->after('jobs');
        });
    }

    public function down(): void
    {
        Schema::table('resumes', function (Blueprint $table): void {
            $table->dropColumn(['title_i18n', 'about_i18n', 'jobs_i18n']);
        });
    }
};
