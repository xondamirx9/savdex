<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Компания — центральная сущность площадки.
 * Лимиты тарифа, кредиты и рейтинг считаются на компанию, а не на пользователя:
 * в одной фирме может быть несколько сотрудников с общим кошельком.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('companies', function (Blueprint $table) {
            $table->id();
            $table->string('slug')->unique();
            $table->string('name');
            $table->string('legal_name')->nullable();
            $table->string('tin', 20)->nullable()->index();      // ИНН / СТИР

            $table->foreignId('country_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('city_id')->nullable()->constrained()->nullOnDelete();
            $table->string('address')->nullable();
            $table->decimal('lat', 10, 7)->nullable();
            $table->decimal('lng', 10, 7)->nullable();

            // производитель / импортёр / дистрибьютор / торговая компания / услуги
            $table->string('type', 32)->nullable();
            // supplier | buyer | both — влияет только на онбординг и подсказки,
            // публиковать оба типа объявлений может любая компания (§4.1 ТЗ)
            $table->string('primary_role', 16)->default('both');

            $table->text('description')->nullable();
            $table->string('logo_path')->nullable();
            $table->string('cover_path')->nullable();
            $table->string('website')->nullable();

            // Контакты. Публично скрыты до оплаты раскрытия (§5.6 ТЗ)
            $table->string('phone', 32)->nullable();
            $table->string('email')->nullable();
            $table->string('telegram', 64)->nullable();
            $table->string('whatsapp', 32)->nullable();
            $table->string('contact_person')->nullable();

            $table->unsignedSmallInteger('founded_year')->nullable();
            $table->string('employees_range', 16)->nullable();
            $table->string('turnover_range', 16)->nullable();

            /**
             * Уровень верификации (§5.3 ТЗ). Выдаётся ТОЛЬКО модерацией
             * и не входит ни в один платный тариф.
             * 0 — не проверена
             * 1 — контакты подтверждены
             * 2 — компания проверена
             * 3 — проверена расширенно
             */
            $table->unsignedTinyInteger('verification_level')->default(0);
            $table->timestamp('verified_at')->nullable();
            $table->foreignId('verified_by')->nullable()->constrained('users')->nullOnDelete();

            // Денормализованные показатели: пересчитываются задачей по расписанию
            $table->decimal('rating', 3, 2)->default(0);
            $table->unsignedInteger('reviews_count')->default(0);
            $table->unsignedInteger('completed_deals_count')->default(0);
            $table->unsignedSmallInteger('response_time_hours')->nullable();

            // active | pending | blocked
            $table->string('status', 16)->default('active')->index();
            $table->text('blocked_reason')->nullable();
            $table->timestamp('blocked_at')->nullable();

            $table->timestamps();
            $table->softDeletes();

            $table->index(['status', 'verification_level']);
            $table->index(['country_id', 'city_id']);
        });

        // Расширяемые поля без миграций (§5.2 FR-COMP-02).
        // Новые атрибуты добавляет суперадмин из админки.
        Schema::create('company_attributes', function (Blueprint $table) {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->string('key', 64);
            $table->text('value')->nullable();
            $table->string('type', 16)->default('string');   // string|number|bool|date|json
            $table->timestamps();

            $table->unique(['company_id', 'key']);
        });

        Schema::create('company_documents', function (Blueprint $table) {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->string('type', 32);                       // registration|license|certificate|quality|presentation
            $table->string('title');
            $table->string('file_path');
            $table->unsignedInteger('file_size')->nullable();
            $table->string('mime', 64)->nullable();
            $table->date('valid_until')->nullable();
            $table->boolean('is_public')->default(true);
            $table->string('moderation_status', 16)->default('pending');  // pending|approved|rejected
            $table->text('moderation_note')->nullable();
            $table->timestamps();

            $table->index(['company_id', 'moderation_status']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('company_documents');
        Schema::dropIfExists('company_attributes');
        Schema::dropIfExists('companies');
    }
};
