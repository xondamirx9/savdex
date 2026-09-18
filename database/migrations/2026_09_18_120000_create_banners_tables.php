<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Баннеры: акции и объявления площадки, которые вешают без разработчика.
 *
 * До этого главная собиралась из семи неизменяемых блоков, и полоса
 * «Скидка до 1 октября» означала задачу разработчику и деплой — то есть
 * акцию нельзя было запустить быстрее, чем за день.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('banners', function (Blueprint $table): void {
            $table->id();

            // Имя для админки: на сайте не показывается, нужно чтобы
            // отличать «Осенняя акция» от «Осенняя акция (2)» в списке
            $table->string('name');

            $table->string('placement');          // home | catalog
            $table->string('url')->nullable();    // куда ведёт; пусто — баннер без ссылки

            /*
             * Текст для незрячих и для случая, когда картинка не
             * загрузилась. Обязателен: баннер без подписи для читалки
             * экрана — пустое место, а не акция.
             */
            $table->string('alt');

            $table->string('image_path');
            $table->string('image_mobile_path')->nullable();

            /*
             * Точка фокуса в процентах — что не обрезать, когда широкую
             * картинку приходится вписывать в узкий экран телефона
             * и отдельной мобильной не загрузили.
             */
            $table->unsignedTinyInteger('focal_x')->default(50);
            $table->unsignedTinyInteger('focal_y')->default(50);

            /*
             * Срок показа. Пустое начало — «сразу», пустой конец —
             * «бессрочно». Баннер с прошедшим концом исчезает сам,
             * снимать его руками не нужно.
             */
            $table->timestamp('starts_at')->nullable();
            $table->timestamp('ends_at')->nullable();

            // Выключатель поверх дат: снять с показа, не трогая сроки
            $table->boolean('is_active')->default(true);

            // Может ли посетитель закрыть баннер крестиком
            $table->boolean('is_dismissible')->default(true);

            // Меньше — выше. На одно место одновременно показывается один
            $table->unsignedSmallInteger('sort')->default(0);

            $table->timestamps();

            // Выборка живого баннера места — по этим трём полям
            $table->index(['placement', 'is_active', 'sort']);
        });

        /*
         * Картинка под язык. Текст акции обычно внутри изображения,
         * и русская полоса на китайской версии сайта выглядит недоделкой.
         *
         * Необязательна: не нашлось перевода — показывается основная.
         */
        Schema::create('banner_images', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('banner_id')->constrained()->cascadeOnDelete();
            $table->string('locale', 5);
            $table->string('image_path');
            $table->string('image_mobile_path')->nullable();
            $table->timestamps();

            $table->unique(['banner_id', 'locale']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('banner_images');
        Schema::dropIfExists('banners');
    }
};
