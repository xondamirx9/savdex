<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Категории деятельности компании.
 *
 * Отдельная таблица связей, а не строки в company_attributes: там
 * стоит unique(company_id, key), то есть больше одного значения
 * с ключом «category» не сохранить. Плюс по этим категориям идёт
 * фильтрация каталога — связь нужна для join, а не для хранения.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('company_category', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->foreignId('category_id')->constrained()->cascadeOnDelete();
            $table->timestamps();

            $table->unique(['company_id', 'category_id']);
            $table->index('category_id');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('company_category');
    }
};
