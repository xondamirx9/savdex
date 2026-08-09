<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Откуда взялась подписка: оплата или решение администратора.
 *
 * Тариф выдают руками чаще, чем кажется: VIP партнёру, продление
 * под дебиторку, компенсация за сбой, тестовый доступ отделу продаж.
 * Без пометки такие подписки неотличимы от оплаченных, и выручка
 * в отчёте оказывается выше реальной ровно на сумму подарков.
 *
 * granted_by с nullOnDelete: удаление сотрудника не должно уносить
 * подписку компании — это разные сущности и разные последствия.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('subscriptions', function (Blueprint $table): void {
            $table->string('source')->default('payment')->after('status'); // payment | manual
            $table->foreignId('granted_by')->nullable()->after('source')->constrained('users')->nullOnDelete();
            $table->string('grant_reason')->nullable()->after('granted_by');
        });
    }

    public function down(): void
    {
        Schema::table('subscriptions', function (Blueprint $table): void {
            $table->dropConstrainedForeignId('granted_by');
            $table->dropColumn(['source', 'grant_reason']);
        });
    }
};
