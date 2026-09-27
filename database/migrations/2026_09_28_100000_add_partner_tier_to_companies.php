<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Партнёры площадки: генеральные и обычные.
 *
 * Раньше страница «Партнёры» сама набирала верхушку проверенных
 * компаний. Партнёрство — договорённость с площадкой, а не уровень
 * проверки, поэтому его назначает администратор: действием
 * «Партнёрство» в списке компаний админки.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            // null — не партнёр; general — генеральный; partner — партнёр
            $table->string('partner_tier', 16)->nullable()->index();
            // Порядок внутри вкладки: меньше — выше
            $table->unsignedInteger('partner_sort')->default(0);
        });
    }

    public function down(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->dropIndex(['partner_tier']);
            $table->dropColumn(['partner_tier', 'partner_sort']);
        });
    }
};
