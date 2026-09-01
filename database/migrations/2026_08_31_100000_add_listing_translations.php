<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Переводы содержимого объявления.
 *
 * Заголовок и описание продавец пишет по-русски, и на остальных
 * языках каталога они оставались русскими. Машинный перевод
 * делается фоном при публикации (TranslateListing) и хранится
 * здесь: {en: ..., uz: ..., tr: ..., zh: ...}.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->json('title_i18n')->nullable()->after('title');
            $table->json('description_i18n')->nullable()->after('description');
        });
    }

    public function down(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->dropColumn(['title_i18n', 'description_i18n']);
        });
    }
};
