<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Объявления: предложения и запросы.
 *
 * Статистика вынесена в отдельную таблицу по дням, а не в счётчики
 * на самом объявлении: аналитика в кабинете строит графики за период
 * и сравнивает с прошлым — из общего счётчика этого не получить.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('listings', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->foreignId('user_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('category_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('city_id')->nullable()->constrained()->nullOnDelete();

            $table->string('type')->default('supply'); // supply | demand

            // Черновик ещё не имеет публичного адреса: slug строится
            // из заголовка и id, а id известен только после сохранения
            $table->string('slug')->nullable()->unique();
            $table->string('title');
            $table->text('description')->nullable();

            $table->decimal('price', 16, 2)->nullable();
            $table->string('currency', 3)->default('UZS');
            $table->string('unit')->nullable();          // т, м³, шт
            $table->boolean('price_negotiable')->default(false);
            $table->unsignedInteger('min_order')->nullable();
            $table->string('delivery_terms')->nullable();
            $table->string('payment_terms')->nullable();

            /*
             * draft — черновик мастера, moderation — на проверке,
             * active — опубликовано, rejected — отклонено модератором,
             * expired — истёк срок, archived — снято владельцем.
             */
            $table->string('status')->default('draft');
            $table->text('moderation_note')->nullable();
            $table->unsignedTinyInteger('wizard_step')->default(1);

            $table->timestamp('published_at')->nullable();
            $table->timestamp('expires_at')->nullable();

            // Денормализованные счётчики — для списков, где N+1 недопустим
            $table->unsignedInteger('impressions_count')->default(0);
            $table->unsignedInteger('views_count')->default(0);
            $table->unsignedInteger('unlocks_count')->default(0);
            $table->unsignedInteger('favorites_count')->default(0);

            $table->timestamps();
            $table->softDeletes();

            $table->index(['company_id', 'status']);
            $table->index(['status', 'published_at']);
            $table->index(['category_id', 'status']);
        });

        Schema::create('listing_images', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('listing_id')->constrained()->cascadeOnDelete();
            $table->string('path');
            $table->unsignedSmallInteger('sort')->default(0);
            $table->timestamps();
        });

        Schema::create('listing_attributes', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('listing_id')->constrained()->cascadeOnDelete();
            $table->string('key');
            $table->string('value');
            $table->timestamps();

            $table->unique(['listing_id', 'key']);
        });

        Schema::create('listing_stats', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('listing_id')->constrained()->cascadeOnDelete();
            $table->date('date');
            $table->unsignedInteger('impressions')->default(0);
            $table->unsignedInteger('views')->default(0);
            $table->unsignedInteger('favorites')->default(0);
            $table->unsignedInteger('unlocks')->default(0);
            $table->timestamps();

            $table->unique(['listing_id', 'date']);
        });

        /*
         * Поисковые запросы, по которым показывалось объявление.
         * Раздел «По каким запросам вас находили» в аналитике.
         */
        Schema::create('search_hits', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->string('query');
            $table->date('date');
            $table->unsignedInteger('impressions')->default(0);
            $table->unsignedInteger('clicks')->default(0);
            $table->timestamps();

            $table->unique(['company_id', 'query', 'date']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('search_hits');
        Schema::dropIfExists('listing_stats');
        Schema::dropIfExists('listing_attributes');
        Schema::dropIfExists('listing_images');
        Schema::dropIfExists('listings');
    }
};
