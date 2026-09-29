<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Почта удалённого аккаунта свободна для новой регистрации.
 *
 * Удаление аккаунта — отключение (deleted_at), а не стирание: запись
 * остаётся, администратор находит её и либо восстанавливает, либо
 * удаляет навсегда. Но уникальный индекс на email считал и отключённые
 * строки, и адрес оставался занят навсегда: регистрация отвечала «адрес
 * уже зарегистрирован», вход — «неверный пароль» (отключённого вход не
 * видит), письмо восстановления не уходило. Выхода не было ни одного.
 *
 * Теперь адрес уникален только среди действующих аккаунтов. Частичный
 * индекс одинаково работает в PostgreSQL и SQLite.
 */
return new class extends Migration
{
    private const INDEX = 'users_email_active_unique';

    public function up(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->dropUnique('users_email_unique');
        });

        DB::statement('create unique index '.self::INDEX.' on users (email) where deleted_at is null');
    }

    public function down(): void
    {
        DB::statement('drop index if exists '.self::INDEX);

        Schema::table('users', function (Blueprint $table): void {
            $table->unique('email');
        });
    }
};
