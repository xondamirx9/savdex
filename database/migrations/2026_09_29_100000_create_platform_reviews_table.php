<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Отзывы о самой площадке SavdEx.
 *
 * Отдельно от reviews: там отзыв компании о компании, привязанный
 * к раскрытию контактов, и он двигает рейтинг поставщика. Здесь —
 * мнение пользователя о площадке, без компании-адресата и без влияния
 * на чей-либо рейтинг.
 *
 * Один отзыв на пользователя: правка возвращает его на проверку, а не
 * добавляет второй — иначе один человек заполнял бы витрину сам.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('platform_reviews', function (Blueprint $table): void {
            $table->id();
            // Удалённая учётная запись не уносит отзыв молча — он
            // остаётся без автора, и модератор решает, что с ним делать
            $table->foreignId('user_id')->nullable()->unique()->constrained()->nullOnDelete();
            // Компания автора на момент отзыва: её название — подпись
            $table->foreignId('company_id')->nullable()->constrained()->nullOnDelete();

            $table->unsignedTinyInteger('rating');                    // 1–5, итоговая
            $table->unsignedTinyInteger('rating_usability')->nullable(); // удобство
            $table->unsignedTinyInteger('rating_search')->nullable();    // поиск партнёров
            $table->unsignedTinyInteger('rating_support')->nullable();   // поддержка

            $table->text('body');
            $table->string('status', 20)->default('moderation'); // moderation | published | hidden
            $table->string('screening_flags')->nullable();

            $table->text('moderator_note')->nullable();
            $table->foreignId('moderated_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamp('moderated_at')->nullable();
            $table->timestamps();

            $table->index(['status', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('platform_reviews');
    }
};
