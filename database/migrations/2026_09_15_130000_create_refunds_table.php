<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Возвраты по платежам.
 *
 * Отдельная запись, а не поле в платеже: возврат бывает частичным,
 * бывает не один, и у каждого своя причина, свой автор и своя дата.
 * Поле хранило бы только последний и стирало бы предыдущие.
 *
 * Платёж при возврате не удаляется и не переписывается задним числом —
 * он получает статус, а история остаётся здесь.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('refunds', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('payment_id')->constrained()->cascadeOnDelete();
            $table->foreignId('company_id')->nullable()->constrained()->nullOnDelete();

            $table->unsignedBigInteger('amount');
            $table->string('currency', 3)->default('UZS');

            // Причина обязательна на уровне формы: возврат без причины
            // невозможно ни проверить, ни объяснить проверяющему
            $table->text('reason');

            // requested | done | rejected
            $table->string('status', 20)->default('requested');

            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->foreignId('decided_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamp('decided_at')->nullable();
            $table->text('decision_note')->nullable();

            $table->timestamps();

            $table->index(['status', 'created_at']);
            $table->index('payment_id');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('refunds');
    }
};
