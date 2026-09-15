<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Переводы новостей на языки витрины.
 *
 * Новость пишется по-русски, а площадка работает на пяти языках: до
 * сих пор узбекская и английская версии раздела показывали русский
 * текст. Хранение — как у объявлений и тендеров: JSON по языкам,
 * наполняется машинным переводом после публикации.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('news_posts', function (Blueprint $table): void {
            $table->json('title_i18n')->nullable()->after('title');
            $table->json('excerpt_i18n')->nullable()->after('excerpt');
            $table->json('body_i18n')->nullable()->after('body');
        });
    }

    public function down(): void
    {
        Schema::table('news_posts', function (Blueprint $table): void {
            $table->dropColumn(['title_i18n', 'excerpt_i18n', 'body_i18n']);
        });
    }
};
