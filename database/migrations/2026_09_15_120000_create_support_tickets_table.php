<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Обращения в поддержку и переписка по ним.
 *
 * Отдельно от сообщений между компаниями (message_threads): там
 * переписка двух клиентов, здесь — клиент и площадка. Смешивать их
 * значит показать сотруднику поддержки чужие коммерческие переговоры.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('support_tickets', function (Blueprint $table): void {
            $table->id();
            $table->string('subject', 200);

            $table->foreignId('user_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('company_id')->nullable()->constrained()->nullOnDelete();
            // Обращение бывает и от того, кто не смог войти: почта
            // и имя записываются строками, а не только ссылкой
            $table->string('author_name', 160)->nullable();
            $table->string('author_email', 160)->nullable();

            $table->foreignId('assignee_id')->nullable()->constrained('users')->nullOnDelete();

            // open | working | waiting | closed
            $table->string('status', 20)->default('open');
            // form | email | phone | chat
            $table->string('channel', 20)->default('form');
            // low | normal | high
            $table->string('priority', 10)->default('normal');

            $table->timestamp('last_reply_at')->nullable();
            $table->timestamp('closed_at')->nullable();

            $table->timestamps();
            $table->softDeletes();

            $table->index(['status', 'created_at']);
            $table->index(['assignee_id', 'status']);
        });

        /*
         * Сообщение в обращении.
         *
         * Флаг is_internal отделяет заметку для своих от ответа клиенту:
         * без него внутренние замечания однажды уедут тому, о ком они
         * написаны.
         */
        Schema::create('support_messages', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('ticket_id')->constrained('support_tickets')->cascadeOnDelete();
            $table->foreignId('author_id')->nullable()->constrained('users')->nullOnDelete();
            $table->boolean('from_staff')->default(false);
            $table->boolean('is_internal')->default(false);
            $table->text('body');
            $table->json('attachments')->nullable();
            $table->timestamps();

            $table->index(['ticket_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('support_messages');
        Schema::dropIfExists('support_tickets');
    }
};
