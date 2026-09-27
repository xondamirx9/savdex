<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Кто регистрируется: юридическое лицо, физическое лицо или фрилансер.
 *
 * Выбор делается на первом шаге регистрации и запоминается у человека
 * (users.account_type): профиль на площадке создаётся вторым шагом,
 * и форма этого шага зависит от выбора. У профиля — его правовая
 * форма (companies.legal_form): по ней витрина подписывает карточку.
 *
 * Все существующие записи — юридические лица: до этой миграции
 * площадка регистрировала только компании.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->string('account_type', 16)->default('legal');
        });

        Schema::table('companies', function (Blueprint $table): void {
            $table->string('legal_form', 16)->default('legal')->index();
        });
    }

    public function down(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->dropColumn('account_type');
        });

        Schema::table('companies', function (Blueprint $table): void {
            $table->dropIndex(['legal_form']);
            $table->dropColumn('legal_form');
        });
    }
};
