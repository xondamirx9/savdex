<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Своё направление деятельности: текст, который компания вводит,
 * выбрав в «Чем занимаетесь» категорию «Другое». Показывается
 * на визитке рядом с типом компании.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->string('custom_category', 80)->nullable();
        });
    }

    public function down(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->dropColumn('custom_category');
        });
    }
};
