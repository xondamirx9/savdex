<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Товары мини-сайта.
 *
 * Не объявления: у объявления срок жизни, модерация, лимит тарифа и
 * место в каталоге площадки. Товар мини-сайта — строка витрины
 * компании на её собственной странице, без всего этого. Объявления
 * компании показываются на сайте рядом с ними сами.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('company_site_products', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->string('title', 190);
            $table->text('description')->nullable();
            $table->decimal('price', 16, 2)->nullable();
            $table->string('currency', 3)->default('UZS');
            $table->string('unit', 30)->nullable();
            $table->string('image_path')->nullable();
            $table->string('thumb_path')->nullable();
            $table->unsignedInteger('sort')->default(0);
            $table->timestamps();

            $table->index(['company_id', 'sort']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('company_site_products');
    }
};
