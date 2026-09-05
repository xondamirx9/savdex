<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Тендеры — объявления о закупках, которые заводит площадка.
 *
 * Отдельная таблица, а не тип объявления: у тендера нет компании-
 * автора на площадке (заказчик — внешняя организация, часто без
 * кабинета), нет цены за единицу и модерации, зато есть срок подачи
 * заявок и ссылка на источник. Переводы — как у объявлений: JSON
 * по языкам, наполняется машинным переводом после публикации.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('tenders', function (Blueprint $table): void {
            $table->id();
            $table->string('slug')->nullable()->unique();
            $table->string('title');
            $table->json('title_i18n')->nullable();
            $table->text('description')->nullable();
            $table->json('description_i18n')->nullable();

            // Заказчик — внешняя организация, текстом: у неё нет карточки
            $table->string('customer')->nullable();
            $table->foreignId('category_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('country_id')->nullable()->constrained()->nullOnDelete();
            $table->string('location')->nullable();

            $table->decimal('budget', 16, 2)->nullable();
            $table->char('currency', 3)->default('UZS');
            $table->timestamp('deadline_at')->nullable();

            $table->string('source_url')->nullable();
            $table->string('contact_name')->nullable();
            $table->string('contact_phone', 40)->nullable();
            $table->string('contact_email')->nullable();

            $table->string('status', 20)->default('draft');
            $table->timestamp('published_at')->nullable();
            $table->unsignedInteger('views_count')->default(0);
            $table->text('search_text')->nullable();

            $table->foreignId('author_id')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();

            $table->index(['status', 'published_at']);
            $table->index(['status', 'deadline_at']);
            $table->index(['category_id', 'status']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('tenders');
    }
};
