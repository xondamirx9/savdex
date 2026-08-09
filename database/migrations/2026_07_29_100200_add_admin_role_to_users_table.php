<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Роль в админке.
 *
 * Отдельная колонка, а не пакет ролей: ролей ровно две и по §6.3 ТЗ
 * больше не планируется. Полноценная система прав (spatie/permission)
 * добавила бы четыре таблицы и слой кеширования ради одного поля.
 *
 * Флаг is_admin остаётся: он отвечает на вопрос «пускать ли в панель»,
 * а admin_role — «что там видно». Разделение нужно, чтобы отозвать
 * доступ целиком одним полем, не разбираясь в роли.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            // moderator | superadmin
            $table->string('admin_role', 20)->nullable()->after('is_admin');
        });

        // Существующие администраторы становятся суперадминами:
        // понизить проще, чем разбираться, почему панель опустела
        DB::table('users')->where('is_admin', true)->update(['admin_role' => 'superadmin']);
    }

    public function down(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->dropColumn('admin_role');
        });
    }
};
