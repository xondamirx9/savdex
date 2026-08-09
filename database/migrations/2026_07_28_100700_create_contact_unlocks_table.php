<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Раскрытие контактов — ядро монетизации (§3 ТЗ).
 *
 * Уникальность по паре компаний, а не по объявлению: кредит списывается
 * за компанию один раз и навсегда. Открыв контакт по одному объявлению,
 * покупатель видит его и во всех остальных — это обещание на витрине,
 * и нарушать его нельзя даже случайно.
 *
 * Одна и та же строка обслуживает оба раздела кабинета:
 * «Мои контакты» (я открыл) и «Кто мной интересуется» (открыли меня).
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('contact_unlocks', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();      // кто открыл
            $table->foreignId('target_company_id')->constrained('companies')->cascadeOnDelete(); // чьи контакты
            $table->foreignId('user_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('listing_id')->nullable()->constrained()->nullOnDelete();

            $table->unsignedTinyInteger('credits_spent')->default(1);

            // Воронка работы с контактом: new → contacted → negotiating → deal | rejected
            $table->string('status')->default('new');
            $table->text('note')->nullable();

            // Жалоба на нерабочий контакт — при подтверждении кредит возвращается
            $table->string('complaint_status')->nullable(); // pending | accepted | declined
            $table->text('complaint_reason')->nullable();
            $table->timestamp('complained_at')->nullable();
            $table->boolean('refunded')->default(false);

            $table->timestamps();

            $table->unique(['company_id', 'target_company_id']);
            $table->index(['target_company_id', 'created_at']);
        });

        /*
         * Избранное — шаг воронки между просмотром и раскрытием контакта.
         */
        Schema::create('favorites', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->foreignId('listing_id')->constrained()->cascadeOnDelete();
            $table->timestamps();

            $table->unique(['user_id', 'listing_id']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('favorites');
        Schema::dropIfExists('contact_unlocks');
    }
};
