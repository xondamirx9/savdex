<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Транзакции платёжных провайдеров.
 *
 * Журнал того, что делала сторона провайдера с нашим счётом. Нужен
 * для двух вещей: идемпотентности колбэков (unique на пару
 * provider + provider_transaction_id) и разбора спорных платежей —
 * сырой payload каждого события сохраняется как есть.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('payment_transactions', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('payment_id')->constrained()->cascadeOnDelete();
            $table->string('provider');                       // uzum | payme | click
            $table->string('provider_transaction_id')->nullable();
            $table->string('state')->default('created');      // created | performed | cancelled
            $table->unsignedBigInteger('amount_minor')->nullable(); // в тийинах
            $table->string('currency', 3)->default('UZS');
            $table->json('payload')->nullable();              // сырой запрос/колбэк провайдера
            $table->timestamp('performed_at')->nullable();
            $table->timestamp('cancelled_at')->nullable();
            $table->timestamps();

            // Замок идемпотентности: один и тот же колбэк провайдера
            // не создаёт вторую запись и не проводит оплату дважды
            $table->unique(['provider', 'provider_transaction_id']);
            $table->index('payment_id');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('payment_transactions');
    }
};
