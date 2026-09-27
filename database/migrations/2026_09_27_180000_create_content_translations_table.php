<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Машинные переводы текстов, у которых нет своих полей под языки.
 *
 * Объявления, тендеры, резюме и новости хранят переводы в столбцах
 * *_i18n. Остальной текст из базы — описание компании, IT-задачи,
 * отзывы, услуги продвижения, характеристики товара — выходил на
 * английскую, узбекскую, турецкую и китайскую версии по-русски.
 * Заводить столбцы под каждое такое поле — десяток миграций; вместо
 * этого перевод хранится по самому тексту: один и тот же текст
 * переводится один раз, изменённый — заново.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('content_translations', function (Blueprint $table): void {
            $table->id();
            // sha1 исходного текста: сам текст может быть длинным,
            // а уникальный индекс по длинному полю не строится
            $table->char('hash', 40);
            $table->string('locale', 8);
            $table->text('source');
            $table->text('translation')->nullable();
            // Неудачные попытки: текст, который переводчик раз за разом
            // не берёт, не должен вечно занимать очередь
            $table->unsignedSmallInteger('attempts')->default(0);
            $table->timestamps();

            $table->unique(['hash', 'locale']);
            $table->index(['translation', 'attempts']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('content_translations');
    }
};
