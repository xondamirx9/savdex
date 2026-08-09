<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Нормализованный текст для поиска.
 *
 * Поиск по `lower(title) like ...` не работает одинаково на разных СУБД:
 * `lower()` в SQLite приводит регистр только у ASCII, кириллицу не трогает,
 * а `LIKE` в PostgreSQL регистрозависим. То есть «цемент» не находил бы
 * «Цемент» — на одной СУБД в тестах, на другой в бою, и по-разному.
 *
 * Приведение регистра делается один раз при сохранении, на стороне PHP,
 * где mb_strtolower работает с кириллицей корректно. Поиск идёт по этой
 * колонке обычным LIKE и ведёт себя одинаково везде.
 *
 * Побочная выгода: колонку можно проиндексировать, а при переходе
 * на полнотекстовый поиск заменить содержимое, не трогая запросы.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->text('search_text')->nullable()->after('description');
        });
    }

    public function down(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->dropColumn('search_text');
        });
    }
};
