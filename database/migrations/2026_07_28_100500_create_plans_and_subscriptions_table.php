<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Тарифы, подписки и кошелёк компании.
 *
 * Цена хранится в базовой валюте (USD) и пересчитывается по курсу ЦБ —
 * подход InvestIn: при скачке курса не нужно править каждый тариф руками.
 * price_uzs — зафиксированная витринная цена, если её задали вручную.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('plans', function (Blueprint $table): void {
            $table->id();
            $table->string('code')->unique(); // free | flash | business | premium
            $table->string('name');
            $table->decimal('price_usd', 10, 2)->default(0);
            $table->unsignedBigInteger('price_uzs')->nullable();
            $table->unsignedSmallInteger('period_days')->default(30);

            // Лимиты. null — безлимит
            $table->unsignedInteger('listings_limit')->nullable();
            $table->unsignedInteger('contacts_limit')->nullable();
            $table->unsignedInteger('promo_units')->default(0);
            $table->unsignedSmallInteger('verification_days')->default(5);
            $table->boolean('advanced_analytics')->default(false);
            $table->boolean('sees_interested_names')->default(false);
            $table->boolean('has_microsite')->default(false);

            $table->unsignedSmallInteger('sort')->default(0);
            $table->boolean('is_active')->default(true);
            $table->timestamps();
        });

        Schema::create('subscriptions', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->foreignId('plan_id')->constrained();
            $table->string('status')->default('active'); // active | cancelled | expired
            $table->timestamp('started_at');
            $table->timestamp('ends_at')->nullable();
            $table->boolean('auto_renew')->default(true);
            $table->timestamp('cancelled_at')->nullable();
            $table->timestamps();

            $table->index(['company_id', 'status']);
        });

        /*
         * Кошелёк компании, а не пользователя: лимиты тарифа считаются
         * на компанию, кредиты — общий кошелёк сотрудников (§3 ТЗ).
         */
        Schema::create('wallets', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->unique()->constrained()->cascadeOnDelete();
            $table->integer('credits')->default(0);
            $table->integer('promo_units')->default(0);
            $table->unsignedInteger('contacts_used_this_period')->default(0);
            $table->timestamp('period_resets_at')->nullable();
            $table->timestamps();
        });

        /*
         * Движение кредитов. Каждое списание и начисление — отдельная
         * строка: остаток обязан быть выводим из истории, иначе спор
         * «у меня списали лишнее» нечем закрыть.
         */
        Schema::create('wallet_transactions', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->foreignId('user_id')->nullable()->constrained()->nullOnDelete();
            $table->string('kind'); // credits | promo_units
            $table->integer('amount'); // отрицательное — списание
            $table->integer('balance_after');
            $table->string('reason'); // unlock | purchase | refund | plan_grant | promotion
            $table->nullableMorphs('subject');
            $table->string('comment')->nullable();
            $table->timestamps();

            $table->index(['company_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('wallet_transactions');
        Schema::dropIfExists('wallets');
        Schema::dropIfExists('subscriptions');
        Schema::dropIfExists('plans');
    }
};
