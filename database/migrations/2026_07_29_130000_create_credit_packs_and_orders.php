<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Покупка тарифов и кредитов.
 *
 * Таблица платежей существовала с самого начала, но писать в неё было
 * некому: тариф назначался вручную из админки, кредиты начислялись
 * оттуда же. Продукт продавал доступ, которого нельзя было купить.
 *
 * Пакеты кредитов — справочник, а не константы: цену пакета правят
 * чаще, чем что-либо ещё на площадке.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('credit_packs', function (Blueprint $table): void {
            $table->id();
            $table->string('code')->unique();
            $table->string('name');
            $table->unsignedInteger('credits');
            $table->decimal('price_usd', 10, 2);
            /*
             * Фиксированная цена в сумах перекрывает пересчёт по курсу —
             * так же, как у тарифов. Круглая цифра на витрине продаёт
             * лучше, чем «131 840 сум», полученные умножением.
             */
            $table->unsignedBigInteger('price_uzs')->nullable();
            $table->unsignedSmallInteger('sort')->default(0);
            $table->boolean('is_active')->default(true);
            $table->timestamps();
        });

        Schema::table('payments', function (Blueprint $table): void {
            /*
             * Номер счёта. Человек называет его в назначении платежа,
             * бухгалтерия ищет по нему поступление — id для этого
             * не годится: он не выглядит как номер документа
             * и выдаёт число заказов на площадке.
             */
            $table->string('number', 20)->nullable()->unique()->after('id');
            $table->foreignId('plan_id')->nullable()->after('subscription_id')->constrained()->nullOnDelete();
            $table->foreignId('credit_pack_id')->nullable()->after('plan_id')->constrained()->nullOnDelete();

            // Кто подтвердил поступление денег и когда
            $table->foreignId('confirmed_by')->nullable()->after('paid_at')->constrained('users')->nullOnDelete();
            $table->text('admin_note')->nullable()->after('confirmed_by');

            $table->index(['status', 'created_at']);
        });

        $now = now();

        DB::table('credit_packs')->insert([
            [
                'code' => 'pack_10', 'name' => '10 контактов', 'credits' => 10,
                'price_usd' => 9, 'price_uzs' => null, 'sort' => 1, 'is_active' => true,
                'created_at' => $now, 'updated_at' => $now,
            ],
            [
                'code' => 'pack_30', 'name' => '30 контактов', 'credits' => 30,
                'price_usd' => 24, 'price_uzs' => null, 'sort' => 2, 'is_active' => true,
                'created_at' => $now, 'updated_at' => $now,
            ],
            [
                'code' => 'pack_100', 'name' => '100 контактов', 'credits' => 100,
                'price_usd' => 69, 'price_uzs' => null, 'sort' => 3, 'is_active' => true,
                'created_at' => $now, 'updated_at' => $now,
            ],
        ]);
    }

    public function down(): void
    {
        Schema::table('payments', function (Blueprint $table): void {
            $table->dropIndex(['status', 'created_at']);
            $table->dropConstrainedForeignId('plan_id');
            $table->dropConstrainedForeignId('credit_pack_id');
            $table->dropConstrainedForeignId('confirmed_by');
            $table->dropColumn(['number', 'admin_note']);
        });

        Schema::dropIfExists('credit_packs');
    }
};
