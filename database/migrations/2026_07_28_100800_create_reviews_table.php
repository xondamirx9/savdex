<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Отзывы о компаниях.
 *
 * Оставить отзыв может только тот, кто оплатил раскрытие контактов —
 * поэтому есть ссылка на unlock. Накрутить рейтинг, не заплатив,
 * невозможно; это же обещание вынесено на витрину (§3 ТЗ).
 *
 * Оценки по критериям хранятся колонками, а не строками: критериев
 * ровно четыре, они не меняются, и агрегаты для карточки компании
 * считаются одним запросом.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('reviews', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();       // о ком
            $table->foreignId('author_company_id')->constrained('companies')->cascadeOnDelete();
            $table->foreignId('author_user_id')->nullable()->constrained('users')->nullOnDelete();
            $table->foreignId('contact_unlock_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('listing_id')->nullable()->constrained()->nullOnDelete();

            $table->unsignedTinyInteger('rating');            // 1–5, итоговая
            $table->unsignedTinyInteger('rating_description')->nullable(); // соответствие описанию
            $table->unsignedTinyInteger('rating_response')->nullable();    // скорость ответа
            $table->unsignedTinyInteger('rating_deadlines')->nullable();   // соблюдение сроков
            $table->unsignedTinyInteger('rating_quality')->nullable();     // качество товара

            $table->text('body');
            $table->boolean('deal_confirmed')->default(false);

            $table->text('reply')->nullable();
            $table->timestamp('replied_at')->nullable();

            // Оспаривание: компания может запросить проверку отзыва
            $table->string('dispute_status')->nullable(); // pending | accepted | declined
            $table->text('dispute_reason')->nullable();

            $table->string('status')->default('published'); // published | hidden | moderation
            $table->timestamps();

            $table->unique(['company_id', 'author_company_id', 'listing_id'], 'reviews_unique_per_deal');
            $table->index(['company_id', 'status']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('reviews');
    }
};
