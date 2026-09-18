<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Привязка Telegram к учётной записи.
 *
 * Бот не может написать первым: пока человек сам не нажал «Старт»
 * у бота площадки, его чат нам неизвестен. Поэтому храним номер чата,
 * полученный при привязке, — без него ссылку на смену пароля отправить
 * некуда. Имя пользователя рядом только для того, чтобы человек видел
 * в настройках, какой именно аккаунт привязан.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->string('telegram_chat_id', 32)->nullable()->after('phone_verified_at')->index();
            $table->string('telegram_username', 64)->nullable()->after('telegram_chat_id');
            $table->timestamp('telegram_linked_at')->nullable()->after('telegram_username');
        });
    }

    public function down(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->dropIndex(['telegram_chat_id']);
            $table->dropColumn(['telegram_chat_id', 'telegram_username', 'telegram_linked_at']);
        });
    }
};
