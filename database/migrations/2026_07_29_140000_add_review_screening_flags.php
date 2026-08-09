<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Отметки автоматической проверки отзыва.
 *
 * Модератор должен видеть, что именно насторожило в тексте, а не
 * перечитывать его в поисках причины. Строкой, а не флагами: причин
 * может быть несколько сразу, а перечислять их колонками значит
 * добавлять миграцию на каждую новую проверку.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('reviews', function (Blueprint $table): void {
            $table->string('screening_flags')->nullable()->after('status');

            // Очередь премодерации открывается по статусу
            $table->index('status');
        });
    }

    public function down(): void
    {
        Schema::table('reviews', function (Blueprint $table): void {
            $table->dropIndex(['status']);
            $table->dropColumn('screening_flags');
        });
    }
};
