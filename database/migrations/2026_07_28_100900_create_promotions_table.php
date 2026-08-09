<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Платное продвижение объявлений (§3 ТЗ).
 *
 * impressions_before/after фиксируются в момент запуска и завершения:
 * в кабинете показывается честный эффект инструмента. Считать его
 * задним числом по общей статистике нельзя — периоды накладываются.
 *
 * Ограниченные места (ТОП категории — 3 позиции, ТОП главной — 6)
 * держатся slots на типе: без этого продвижение продаётся бесконечно
 * и перестаёт работать у всех сразу.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('promotion_types', function (Blueprint $table): void {
            $table->id();
            $table->string('code')->unique(); // bump | category_top | urgent | highlight | home_top | mailing
            $table->string('name');
            $table->string('description');
            $table->string('effect_hint')->nullable();
            $table->unsignedSmallInteger('cost_units');
            $table->unsignedSmallInteger('duration_days')->default(0); // 0 — разовое
            $table->unsignedSmallInteger('slots')->nullable();          // null — не ограничено
            $table->string('badge')->nullable();
            $table->string('icon')->nullable();
            $table->unsignedSmallInteger('sort')->default(0);
            $table->boolean('is_active')->default(true);
            $table->timestamps();
        });

        Schema::create('promotions', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('listing_id')->constrained()->cascadeOnDelete();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->foreignId('promotion_type_id')->constrained();
            $table->foreignId('category_id')->nullable()->constrained()->nullOnDelete();

            $table->unsignedSmallInteger('units_spent');
            $table->string('status')->default('active'); // active | finished | queued
            $table->timestamp('starts_at');
            $table->timestamp('ends_at')->nullable();

            $table->unsignedInteger('impressions_before')->default(0);
            $table->unsignedInteger('impressions_after')->nullable();

            $table->timestamps();

            $table->index(['company_id', 'status']);
            $table->index(['listing_id', 'status']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('promotions');
        Schema::dropIfExists('promotion_types');
    }
};
