<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Лента событий и настройки уведомлений.
 *
 * События хранятся строками, а не собираются на лету из пяти таблиц:
 * лента на дашборде должна открываться одним запросом, а UNION по
 * раскрытиям, отзывам, модерации и продвижениям растёт с базой.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('activity_events', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->string('type'); // unlock | review | promotion | moderation | expiry | payment
            $table->string('tone')->default('info'); // info | success | warning | danger
            $table->string('message');
            $table->string('url')->nullable();
            $table->nullableMorphs('subject');
            $table->timestamp('read_at')->nullable();
            $table->timestamps();

            $table->index(['company_id', 'created_at']);
        });

        Schema::create('notification_preferences', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('event'); // contact_unlocked | new_review | moderation | listing_expiring | digest
            $table->boolean('email')->default(true);
            $table->boolean('telegram')->default(false);
            $table->timestamps();

            $table->unique(['user_id', 'event']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('notification_preferences');
        Schema::dropIfExists('activity_events');
    }
};
