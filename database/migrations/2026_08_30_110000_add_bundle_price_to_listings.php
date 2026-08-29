<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Цена за весь комплект — рядом с ценой за единицу.
 *
 * Товар нередко продаётся набором («комплект из 5 шт»), и цена
 * единицы не отвечает на главный вопрос покупателя — сколько стоит
 * весь набор. Поле необязательное: у большинства позиций комплекта
 * нет, и пустая колонка ничего не показывает.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->decimal('bundle_price', 14, 2)->nullable();
        });
    }

    public function down(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->dropColumn('bundle_price');
        });
    }
};
