<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Выбранные владельцем теги объявления.
 *
 * Пусто — теги подбираются автоматически из данных объявления.
 * Заполнено — показывается выбор владельца, но выбирает он только
 * из предложенного площадкой списка: произвольный текст сервер
 * отбрасывает, поэтому колонка никогда не содержит самописных слов.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->json('tags')->nullable();
        });
    }

    public function down(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->dropColumn('tags');
        });
    }
};
