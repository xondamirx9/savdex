<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * CRM площадки: контакты, лиды, сделки, задачи, коммуникации.
 *
 * Пять таблиц заводятся одной миграцией: по отдельности ни одна из них
 * не работает, и откатывать их тоже придётся вместе.
 *
 * Компании и сотрудники не дублируются — CRM ссылается на companies и
 * users. Вторая карточка той же компании разошлась бы с первой в первый
 * же месяц, и дальше никто бы не знал, какая верная.
 */
return new class extends Migration
{
    public function up(): void
    {
        /*
         * Контакт — человек, а не учётная запись.
         *
         * Отдельно от users: у контакта может не быть регистрации на
         * площадке, а у компании контактов несколько — снабженец,
         * бухгалтер, директор.
         */
        Schema::create('crm_contacts', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->nullable()->constrained()->nullOnDelete();
            $table->string('name', 160);
            $table->string('position', 120)->nullable();
            $table->string('phone', 40)->nullable();
            $table->string('email', 160)->nullable();
            $table->string('telegram', 80)->nullable();
            $table->text('note')->nullable();
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();
            $table->softDeletes();

            $table->index('company_id');
            $table->index('name');
        });

        /*
         * Лид — обращение, из которого может вырасти клиент.
         *
         * Контактные данные лежат и строками, и ссылкой на контакт:
         * заявка приходит с именем и телефоном, а карточку контакта
         * заводят позже, когда становится понятно, что это не случайность.
         */
        Schema::create('crm_leads', function (Blueprint $table): void {
            $table->id();
            $table->string('title', 200);
            $table->string('source', 40)->default('site');
            $table->foreignId('company_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('contact_id')->nullable()->constrained('crm_contacts')->nullOnDelete();

            $table->string('contact_name', 160)->nullable();
            $table->string('contact_phone', 40)->nullable();
            $table->string('contact_email', 160)->nullable();

            // Пустой ответственный — намеренно: новая заявка видна всем
            // продавцам, иначе она зависнет до первого распределения
            $table->foreignId('owner_id')->nullable()->constrained('users')->nullOnDelete();

            // new | working | qualified | converted | lost
            $table->string('status', 20)->default('new');
            $table->text('lost_reason')->nullable();
            $table->text('note')->nullable();

            $table->timestamps();
            $table->softDeletes();

            $table->index(['status', 'created_at']);
            $table->index(['owner_id', 'status']);
        });

        /*
         * Сделка — работа с клиентом по конкретной сумме.
         *
         * Сумма целым числом в минимальных единицах валюты: сумы без
         * копеек, а дробное хранение денег однажды покажет 1 999 999.99
         * там, где должно стоять два миллиона.
         */
        Schema::create('crm_deals', function (Blueprint $table): void {
            $table->id();
            $table->string('title', 200);
            $table->foreignId('company_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('contact_id')->nullable()->constrained('crm_contacts')->nullOnDelete();
            $table->foreignId('lead_id')->nullable()->constrained('crm_leads')->nullOnDelete();
            $table->foreignId('owner_id')->nullable()->constrained('users')->nullOnDelete();

            $table->unsignedBigInteger('amount')->default(0);
            $table->string('currency', 3)->default('UZS');

            // new | negotiation | proposal | won | lost
            $table->string('stage', 20)->default('new');
            $table->date('expected_close_at')->nullable();
            $table->timestamp('closed_at')->nullable();
            $table->text('lost_reason')->nullable();
            $table->text('note')->nullable();

            $table->timestamps();
            $table->softDeletes();

            $table->index(['stage', 'expected_close_at']);
            $table->index(['owner_id', 'stage']);
        });

        /*
         * Задача — что сделать и к какому сроку.
         *
         * Привязка полиморфная: задача бывает и по лиду, и по сделке,
         * и по компании. Три отдельные колонки под каждый случай
         * означали бы, что две из них всегда пусты.
         */
        Schema::create('crm_tasks', function (Blueprint $table): void {
            $table->id();
            $table->string('title', 200);
            $table->text('description')->nullable();
            $table->foreignId('assignee_id')->nullable()->constrained('users')->nullOnDelete();
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamp('due_at')->nullable();
            $table->timestamp('done_at')->nullable();
            $table->nullableMorphs('subject');
            $table->timestamps();
            $table->softDeletes();

            $table->index(['assignee_id', 'done_at']);
            $table->index('due_at');
        });

        /*
         * Коммуникация — запись состоявшегося разговора.
         *
         * Заводится руками: интеграции с почтой и телефонией пока нет,
         * и это отдельный разговор. Но история переговоров нужна уже
         * сейчас, иначе она живёт в голове одного продавца.
         */
        Schema::create('crm_communications', function (Blueprint $table): void {
            $table->id();
            // call | email | meeting | message
            $table->string('type', 20)->default('call');
            $table->timestamp('happened_at');
            $table->string('summary', 200);
            $table->text('body')->nullable();
            $table->foreignId('author_id')->nullable()->constrained('users')->nullOnDelete();
            $table->foreignId('contact_id')->nullable()->constrained('crm_contacts')->nullOnDelete();
            $table->nullableMorphs('subject');
            $table->timestamps();

            $table->index(['author_id', 'happened_at']);
            $table->index('happened_at');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('crm_communications');
        Schema::dropIfExists('crm_tasks');
        Schema::dropIfExists('crm_deals');
        Schema::dropIfExists('crm_leads');
        Schema::dropIfExists('crm_contacts');
    }
};
