<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Штатная таблица уведомлений Laravel.
 *
 * Отдельно от user_notifications: та обслуживает продуктовые
 * уведомления пользователю (открыли контакт, новый отзыв), а эта —
 * системные сообщения фреймворка и Filament, вроде «выгрузка готова».
 *
 * Без неё Filament молча терял уведомления о готовности экспорта:
 * задание падало, а администратор ждал файл, который не появится.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('notifications', function (Blueprint $table): void {
            $table->uuid('id')->primary();
            $table->string('type');
            $table->morphs('notifiable');
            $table->text('data');
            $table->timestamp('read_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('notifications');
    }
};
