<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Расширение стандартной таблицы users под нужды площадки.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->foreignId('company_id')->nullable()->after('id')
                ->constrained()->nullOnDelete();

            $table->string('phone', 32)->nullable()->after('email');
            $table->timestamp('phone_verified_at')->nullable()->after('phone');
            $table->string('locale', 5)->default('ru')->after('phone_verified_at');

            // owner | manager — роль внутри компании.
            // Административные роли (moderator, sales, support, super_admin)
            // выдаются через spatie/laravel-permission, а не этим полем.
            $table->string('company_role', 16)->default('owner')->after('locale');

            $table->boolean('is_admin')->default(false)->after('company_role');

            /**
             * Учётная запись, созданная суперадмином вручную (§6.3 FR-ADM-03),
             * обязана сменить пароль при первом входе.
             */
            $table->boolean('must_change_password')->default(false)->after('is_admin');

            $table->string('two_factor_secret')->nullable()->after('must_change_password');
            $table->timestamp('two_factor_confirmed_at')->nullable()->after('two_factor_secret');

            $table->timestamp('last_login_at')->nullable();
            $table->string('last_login_ip', 45)->nullable();

            // active | blocked
            $table->string('status', 16)->default('active');

            $table->softDeletes();

            $table->index(['company_id', 'status']);
        });

        // Приглашения сотрудников в компанию
        Schema::create('company_invitations', function (Blueprint $table) {
            $table->id();
            $table->foreignId('company_id')->constrained()->cascadeOnDelete();
            $table->foreignId('invited_by')->constrained('users')->cascadeOnDelete();
            $table->string('email');
            $table->string('company_role', 16)->default('manager');
            $table->string('token', 64)->unique();
            $table->timestamp('expires_at');
            $table->timestamp('accepted_at')->nullable();
            $table->timestamps();

            $table->index(['company_id', 'email']);
        });

        /**
         * Журнал попыток входа. Нужен для NEG-02 и NEG-03 из QA.md:
         * счётчик неудачных попыток должен жить на сервере, а не в сессии,
         * иначе блокировка обходится очисткой cookie.
         */
        Schema::create('login_attempts', function (Blueprint $table) {
            $table->id();
            $table->string('email')->index();
            $table->string('ip', 45)->index();
            $table->boolean('successful')->default(false);
            $table->string('user_agent_hash', 64)->nullable();
            $table->timestamp('created_at')->nullable();

            $table->index(['email', 'ip', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('login_attempts');
        Schema::dropIfExists('company_invitations');

        Schema::table('users', function (Blueprint $table) {
            $table->dropConstrainedForeignId('company_id');
            $table->dropColumn([
                'phone', 'phone_verified_at', 'locale', 'company_role', 'is_admin',
                'must_change_password', 'two_factor_secret', 'two_factor_confirmed_at',
                'last_login_at', 'last_login_ip', 'status', 'deleted_at',
            ]);
        });
    }
};
