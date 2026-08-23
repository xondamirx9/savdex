<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Скидочные промокоды: процент вместо бесплатного периода.
 *
 * Один и тот же код бывает двух видов, и вид определяется полем
 * discount_percent: пусто — код на бесплатный период (как раньше),
 * 1–99 — скидка на оплату тарифа. Активация скидочного кода не выдаёт
 * тариф, а выставляет счёт на остаток цены и уводит на онлайн-оплату.
 *
 * Счёт помнит свой промокод (promo_code_id): по оплате код связывается
 * с выданной подпиской, а по отмене счёта — освобождается и может быть
 * активирован снова.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('promo_codes', function (Blueprint $table): void {
            $table->unsignedTinyInteger('discount_percent')->nullable()->after('days');
        });

        Schema::table('payments', function (Blueprint $table): void {
            $table->foreignId('promo_code_id')->nullable()->constrained()->nullOnDelete();
        });
    }

    public function down(): void
    {
        Schema::table('payments', function (Blueprint $table): void {
            $table->dropConstrainedForeignId('promo_code_id');
        });

        Schema::table('promo_codes', function (Blueprint $table): void {
            $table->dropColumn('discount_percent');
        });
    }
};
