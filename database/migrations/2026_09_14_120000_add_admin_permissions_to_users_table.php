<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Персональные добавки к правам администратора.
 *
 * Роль задаёт базовый набор, а сюда попадают исключения для конкретного
 * человека: «этому администратору дополнительно открыть счета», «у этого
 * модератора отобрать удаление». Роль при этом не меняется — иначе ради
 * одного исключения пришлось бы заводить десятую роль, потом одиннадцатую.
 *
 *     {"grant": ["payments.view"], "revoke": ["companies.delete"]}
 *
 * Колонка admin_role остаётся прежней: moderator и superadmin входят в
 * новый список ролей под теми же именами, и ни одна строка не переписывается.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->json('admin_permissions')->nullable()->after('admin_role');
        });
    }

    public function down(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->dropColumn('admin_permissions');
        });
    }
};
