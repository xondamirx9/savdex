<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Чат между компаниями: отклики на объявления и переписка по ним.
 *
 * Тред всегда парный — покупатель (кто откликнулся) и продавец
 * (владелец объявления), поэтому отметки прочтения лежат прямо на
 * треде двумя колонками, а не отдельной таблицей: непрочитанное для
 * стороны — это сообщения собеседника после её отметки.
 *
 * Объявление в треде nullable: снятое или удалённое объявление не
 * должно обрывать уже начатый разговор о поставке.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('message_threads', function (Blueprint $table): void {
            $table->id();

            $table->foreignId('listing_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('buyer_company_id')->constrained('companies')->cascadeOnDelete();
            $table->foreignId('seller_company_id')->constrained('companies')->cascadeOnDelete();

            // Один тред на пару «объявление + откликнувшаяся компания»:
            // повторный отклик продолжает разговор, а не плодит копии
            $table->unique(['listing_id', 'buyer_company_id']);

            $table->timestamp('buyer_read_at')->nullable();
            $table->timestamp('seller_read_at')->nullable();

            // Денормализовано для сортировки списка: свежий разговор сверху
            $table->timestamp('last_message_at')->nullable();

            $table->timestamps();

            $table->index(['buyer_company_id', 'last_message_at']);
            $table->index(['seller_company_id', 'last_message_at']);
        });

        Schema::create('messages', function (Blueprint $table): void {
            $table->id();

            $table->foreignId('thread_id')->constrained('message_threads')->cascadeOnDelete();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->foreignId('user_id')->nullable()->constrained()->nullOnDelete();

            $table->text('body');

            $table->timestamps();

            $table->index(['thread_id', 'created_at']);
        });

        // Отклики — месячная квота тарифа, как и раскрытия контактов
        Schema::table('wallets', function (Blueprint $table): void {
            $table->unsignedInteger('responses_used_this_period')->default(0);
        });
    }

    public function down(): void
    {
        Schema::table('wallets', function (Blueprint $table): void {
            $table->dropColumn('responses_used_this_period');
        });

        Schema::dropIfExists('messages');
        Schema::dropIfExists('message_threads');
    }
};
