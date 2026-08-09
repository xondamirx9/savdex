<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Содержимое сайта, редактируемое из админки (§6.5, §6.6 ТЗ).
 *
 * Новости, страницы, блоки главной и настройки площадки. Тексты,
 * которые сейчас лежат в коде, переезжают сюда: править витрину
 * не должно означать выкатывать релиз.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('news_posts', function (Blueprint $table): void {
            $table->id();
            $table->string('slug')->unique();
            $table->string('category');
            $table->string('title');
            $table->text('excerpt');
            $table->longText('body');
            $table->string('image_path')->nullable();
            $table->string('read_time')->nullable();

            $table->boolean('is_published')->default(false);
            $table->timestamp('published_at')->nullable();
            $table->unsignedSmallInteger('sort')->default(0);

            $table->foreignId('author_id')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();

            $table->index(['is_published', 'published_at']);
        });

        /*
         * Страницы: «О нас», «Контакты», «Помощь», оферта, политика.
         * Ключ вместо адреса: страница может переехать, а ссылки в коде
         * должны остаться рабочими.
         */
        Schema::create('pages', function (Blueprint $table): void {
            $table->id();
            $table->string('key')->unique();
            $table->string('slug')->unique();
            $table->string('title');
            $table->text('excerpt')->nullable();
            $table->longText('body')->nullable();

            $table->string('meta_title')->nullable();
            $table->string('meta_description')->nullable();

            $table->boolean('is_published')->default(true);
            $table->unsignedSmallInteger('sort')->default(0);
            $table->timestamps();
        });

        /*
         * Блоки главной страницы: порядок, тексты, видимость (§6.5 ТЗ).
         * Именно это заказчик просил вынести в админку в первую очередь.
         */
        Schema::create('landing_blocks', function (Blueprint $table): void {
            $table->id();
            $table->string('key')->unique();
            $table->string('name');
            $table->string('eyebrow')->nullable();
            $table->string('heading')->nullable();
            $table->text('subheading')->nullable();
            $table->json('payload')->nullable();

            $table->boolean('is_visible')->default(true);
            $table->unsignedSmallInteger('sort')->default(0);
            $table->timestamps();

            $table->index(['is_visible', 'sort']);
        });

        /*
         * Настройки площадки: контакты, реквизиты, соцсети, тексты
         * подвала. Значение — json, чтобы одинаково хранить строку,
         * число и список без колонки под каждый тип.
         */
        Schema::create('settings', function (Blueprint $table): void {
            $table->id();
            $table->string('group', 40)->default('general');
            $table->string('key')->unique();
            $table->string('label');
            $table->text('description')->nullable();
            $table->string('type', 20)->default('string'); // string|text|number|bool|json
            $table->json('value')->nullable();
            $table->unsignedSmallInteger('sort')->default(0);
            $table->timestamps();

            $table->index('group');
        });

        Schema::create('faq_items', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('page_id')->nullable()->constrained('pages')->cascadeOnDelete();
            $table->string('question');
            $table->text('answer');
            $table->unsignedSmallInteger('sort')->default(0);
            $table->boolean('is_published')->default(true);
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('faq_items');
        Schema::dropIfExists('settings');
        Schema::dropIfExists('landing_blocks');
        Schema::dropIfExists('pages');
        Schema::dropIfExists('news_posts');
    }
};
