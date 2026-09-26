<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Мини-сайт компании на acme.savdex.site.
 *
 * Сам сайт содержимого не хранит: товары, контакты, документы и отзывы
 * берутся из карточки компании. Здесь только адрес и оформление.
 *
 * Оформление хранится дважды — черновик и опубликованное. Компания
 * подбирает цвета сколько угодно, а посетители видят прежний вид,
 * пока она не нажмёт «Опубликовать».
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('company_sites', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->unique()->constrained()->cascadeOnDelete();
            $table->string('subdomain', 40)->unique();
            $table->string('status', 16)->default('draft');
            $table->json('theme')->nullable();
            $table->json('published_theme')->nullable();
            $table->timestamp('published_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('company_sites');
    }
};
