<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * IT-услуги: компании публикуют IT-задачи, IT-исполнители откликаются.
 *
 * Отдельная таблица, а не тип объявления: у задачи нет цены за единицу,
 * категории каталога и модерации, зато есть бюджет диапазоном, срок,
 * стек технологий и файлы ТЗ. Отклик ведёт в тот же чат, что и отклик
 * на объявление, — тред получает it_task_id вместо listing_id.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('it_tasks', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->foreignId('user_id')->nullable()->constrained()->nullOnDelete();
            $table->string('slug')->nullable()->unique();
            $table->string('title');
            $table->text('description');
            $table->string('service_type', 32);
            $table->json('stack')->nullable();

            $table->string('budget_type', 16)->default('negotiable');
            $table->decimal('budget_from', 16, 2)->nullable();
            $table->decimal('budget_to', 16, 2)->nullable();
            $table->char('currency', 3)->default('UZS');
            $table->date('deadline_at')->nullable();

            $table->string('status', 16)->default('active');
            $table->timestamp('published_at')->nullable();
            $table->timestamp('closed_at')->nullable();
            $table->unsignedInteger('responses_count')->default(0);
            $table->unsignedInteger('views_count')->default(0);
            $table->text('search_text')->nullable();
            $table->timestamps();

            $table->index(['status', 'published_at']);
            $table->index(['company_id', 'status']);
            $table->index(['service_type', 'status']);
        });

        Schema::create('it_task_files', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('it_task_id')->constrained('it_tasks')->cascadeOnDelete();
            $table->string('title');
            $table->string('file_path');
            $table->unsignedBigInteger('file_size')->default(0);
            $table->string('mime')->nullable();
            $table->timestamps();
        });

        // Тред чата — либо по объявлению, либо по IT-задаче
        Schema::table('message_threads', function (Blueprint $table): void {
            $table->foreignId('it_task_id')->nullable()->after('listing_id')
                ->constrained('it_tasks')->nullOnDelete();
            $table->unique(['it_task_id', 'buyer_company_id']);
        });

        // Роль IT-исполнителя: только с ней видна кнопка «Откликнуться»
        Schema::table('companies', function (Blueprint $table): void {
            $table->boolean('is_it_provider')->default(false)->after('primary_role');
            $table->json('it_specializations')->nullable()->after('is_it_provider');
        });
    }

    public function down(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->dropColumn(['is_it_provider', 'it_specializations']);
        });

        Schema::table('message_threads', function (Blueprint $table): void {
            $table->dropUnique(['it_task_id', 'buyer_company_id']);
            $table->dropConstrainedForeignId('it_task_id');
        });

        Schema::dropIfExists('it_task_files');
        Schema::dropIfExists('it_tasks');
    }
};
