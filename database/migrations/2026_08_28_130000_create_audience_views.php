<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Кто смотрел компанию: просмотры объявлений и визитки с указанием
 * зрителя.
 *
 * Счётчики показов и просмотров обезличены — они отвечают «сколько»,
 * но не «кто». Здесь хранится именно «кто»: строка пишется только
 * когда смотрит авторизованный пользователь с компанией, и не пишется
 * для своих же страниц. Гости в таблицу не попадают вовсе — им
 * нечего показать в разделе «Кто мной интересуется».
 *
 * listing_id пуст ТОЛЬКО у просмотра визитки компании — на этом
 * держится подпись «что смотрели». Поэтому каскад, а не nullOnDelete:
 * обнуление ссылки при удалении объявления выдавало бы его просмотры
 * за просмотры визитки. Обычное удаление объявлений мягкое и строк
 * не трогает; жёсткое (суперадмин) уносит их с собой — честнее,
 * чем врать про визитку.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('audience_views', function (Blueprint $table): void {
            $table->id();

            // Чью аудиторию пополнил просмотр — по этой колонке кабинет
            // выбирает «кто смотрел меня», отсюда и составной индекс с датой
            $table->foreignId('target_company_id')->constrained('companies')->cascadeOnDelete();
            $table->foreignId('viewer_company_id')->constrained('companies')->cascadeOnDelete();
            $table->foreignId('listing_id')->nullable()->constrained('listings')->cascadeOnDelete();

            $table->timestamps();

            $table->index(['target_company_id', 'created_at']);

            // Дедупликация на стороне базы: «этот зритель уже засчитан
            // недавно?» — сессионный кэш обходится сбросом куки
            $table->index(['viewer_company_id', 'target_company_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('audience_views');
    }
};
