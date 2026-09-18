<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Резюме соискателя.
 *
 * Площадка сводит компании с компаниями, но людей ищут те же самые
 * компании: закупщика, логиста, технолога. Раздел бесплатный — это
 * не товар, а способ привести на площадку тех, кто потом заведёт
 * на ней компанию.
 *
 * Резюме одно на человека: меню кабинета называется «Моё резюме»,
 * и второе завести нельзя — у соискателя одна трудовая биография,
 * а разные должности живут в поле «Кем хочу работать».
 *
 * Опыт, образование и языки лежат json-списками, а не отдельными
 * таблицами: их показывают и правят целиком, и ни один запрос
 * не ищет «всех, кто работал в такой-то компании».
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('resumes', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('user_id')->unique()->constrained()->cascadeOnDelete();
            // Адрес строится из должности и номера, а номер известен
            // только после сохранения — поэтому допускаем пустой
            $table->string('slug')->nullable()->unique();

            // Кем хочу работать и в какой сфере
            $table->string('title', 120);
            $table->string('field', 40)->nullable()->index();

            $table->foreignId('country_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('city_id')->nullable()->constrained()->nullOnDelete();

            $table->unsignedInteger('salary')->nullable();
            $table->string('currency', 3)->default('UZS');

            /*
             * Занятость и график — списками: человек готов и на полный
             * день, и на проект, и заставлять его выбирать одно значит
             * терять половину откликов.
             */
            $table->json('employment')->nullable();
            $table->json('schedule')->nullable();

            // Считается из мест работы при сохранении: по нему идёт
            // фильтр «опыт от трёх лет», а складывать периоды в запросе
            // нельзя — они лежат в json
            $table->unsignedSmallInteger('experience_months')->default(0);

            $table->text('about')->nullable();
            $table->json('skills')->nullable();
            $table->json('jobs')->nullable();
            $table->json('education')->nullable();
            $table->json('languages')->nullable();

            $table->string('photo_path')->nullable();

            /*
             * Контакты: раздел бесплатный, и компания видит их сразу.
             * Но что именно показывать, решает соискатель — телефон
             * можно спрятать и оставить переписку на площадке.
             */
            $table->string('contact_name')->nullable();
            $table->string('contact_phone', 32)->nullable();
            $table->string('contact_email')->nullable();
            $table->boolean('show_phone')->default(true);
            $table->boolean('show_email')->default(true);

            // draft — виден только владельцу, published — в разделе,
            // hidden — снят самим человеком, blocked — снят модерацией
            $table->string('status', 16)->default('draft')->index();
            $table->string('moderation_note')->nullable();
            $table->timestamp('published_at')->nullable();
            $table->unsignedInteger('views_count')->default(0);

            $table->timestamps();
            $table->softDeletes();

            $table->index(['status', 'published_at']);
            $table->index(['status', 'field']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('resumes');
    }
};
