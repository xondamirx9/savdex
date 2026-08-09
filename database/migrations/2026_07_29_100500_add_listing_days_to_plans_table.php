<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Срок жизни объявления зависит от тарифа (§3.3 ТЗ).
 *
 * Раньше константа Listing::LIFETIME_DAYS = 90 применялась ко всем:
 * бесплатный пользователь получал ровно то, за что должен платить
 * Business, и одна из причин перейти на платный тариф исчезала.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('plans', function (Blueprint $table): void {
            $table->unsignedSmallInteger('listing_days')->default(30)->after('period_days');
        });
    }

    public function down(): void
    {
        Schema::table('plans', function (Blueprint $table): void {
            $table->dropColumn('listing_days');
        });
    }
};
