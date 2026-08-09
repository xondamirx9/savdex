<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Уведомления пользователя.
 *
 * Отдельно от activity_events: события — это лента компании («открыли
 * контакт», «истекает объявление»), а уведомления адресованы конкретному
 * человеку и имеют состояние прочтения. Одно событие может породить
 * уведомления нескольким сотрудникам с разными настройками каналов.
 *
 * Своя таблица, а не штатная notifications Laravel: нужны рассылки
 * от администратора с адресацией по сегментам и ссылка на автора.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('user_notifications', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->foreignId('company_id')->nullable()->constrained()->cascadeOnDelete();

            // contact_unlocked | new_review | moderation | listing_expiring | payment | broadcast
            $table->string('type');
            $table->string('tone')->default('info'); // info | success | warning | danger
            $table->string('title');
            $table->text('body')->nullable();
            $table->string('url')->nullable();
            $table->nullableMorphs('subject');

            /*
             * Рассылка от администратора. Хранится автор — при разборе
             * жалобы «кто это отправил» ответ должен быть в системе,
             * а не в переписке.
             */
            $table->foreignId('sent_by')->nullable()->constrained('users')->nullOnDelete();
            $table->boolean('is_broadcast')->default(false);

            $table->timestamp('read_at')->nullable();
            $table->timestamps();

            $table->index(['user_id', 'read_at']);
            $table->index(['user_id', 'created_at']);
        });

        /*
         * Рассылки администратора: одна запись на отправку, из неё
         * порождаются персональные уведомления. Нужна, чтобы видеть
         * историю рассылок и охват, не собирая её из тысяч строк.
         */
        Schema::create('broadcasts', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('sent_by')->nullable()->constrained('users')->nullOnDelete();
            $table->string('title');
            $table->text('body');
            $table->string('url')->nullable();
            $table->string('tone')->default('info');

            // all | plan | verified | unverified | role
            $table->string('audience')->default('all');
            $table->string('audience_value')->nullable();

            $table->unsignedInteger('recipients_count')->default(0);
            $table->timestamp('sent_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('broadcasts');
        Schema::dropIfExists('user_notifications');
    }
};
