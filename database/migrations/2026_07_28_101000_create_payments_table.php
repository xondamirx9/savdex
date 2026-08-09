<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Платежи и привязанные карты (§11 ТЗ).
 *
 * Номер карты не хранится — только токен платёжной системы, маска
 * последних четырёх цифр и срок. Это не осторожность, а условие работы
 * с Payme Subscribe: полный номер площадке не передаётся вовсе.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('payment_methods', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->string('provider');           // payme | click | uzum | paddle
            $table->string('token');              // токен провайдера, не номер карты
            $table->string('brand')->nullable();  // Uzcard | Humo | Visa
            $table->string('last4', 4);
            $table->string('expires', 5)->nullable(); // MM/YY
            $table->boolean('is_default')->default(false);
            $table->timestamps();

            $table->index(['company_id', 'is_default']);
        });

        Schema::create('payments', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->foreignId('payment_method_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('subscription_id')->nullable()->constrained()->nullOnDelete();

            $table->string('purpose');            // subscription | credits | promo_units
            $table->string('description');
            $table->unsignedBigInteger('amount'); // в сумах, копейки не нужны
            $table->string('currency', 3)->default('UZS');
            $table->string('provider')->nullable();
            $table->string('external_id')->nullable();
            $table->string('status')->default('pending'); // pending | paid | failed | refunded
            $table->timestamp('paid_at')->nullable();
            $table->string('invoice_path')->nullable();

            $table->timestamps();

            $table->index(['company_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('payments');
        Schema::dropIfExists('payment_methods');
    }
};
