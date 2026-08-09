<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Категории объявлений — дерево на два уровня.
 *
 * Названия вынесены в отдельную таблицу переводов: площадка работает
 * на пяти языках (§13 ТЗ), и держать их колонками name_ru, name_uz…
 * значит менять схему при добавлении языка.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('categories', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('parent_id')->nullable()->constrained('categories')->nullOnDelete();
            $table->string('slug')->unique();
            $table->string('icon')->nullable();
            $table->unsignedSmallInteger('sort')->default(0);
            $table->boolean('is_active')->default(true);
            $table->timestamps();

            $table->index(['parent_id', 'sort']);
        });

        Schema::create('category_translations', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('category_id')->constrained()->cascadeOnDelete();
            $table->string('locale', 5);
            $table->string('name');
            $table->timestamps();

            $table->unique(['category_id', 'locale']);
        });

        /*
         * Поля, специфичные для категории: марка цемента, состав ткани,
         * толщина металла. В прототипе — блок «Поля категории
         * подставляются автоматически» в мастере создания объявления.
         */
        Schema::create('category_fields', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('category_id')->constrained()->cascadeOnDelete();
            $table->string('key');
            $table->string('label');
            $table->string('type')->default('select'); // select | text | number
            $table->json('options')->nullable();
            $table->string('unit')->nullable();
            $table->boolean('is_required')->default(false);
            $table->unsignedSmallInteger('sort')->default(0);
            $table->timestamps();

            $table->unique(['category_id', 'key']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('category_fields');
        Schema::dropIfExists('category_translations');
        Schema::dropIfExists('categories');
    }
};
