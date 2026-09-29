<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Раздел «Пользователи» в админке Django: отключение и восстановление
 * аккаунта (deleted_at, как SoftDeletes; updated_at выдан раньше) и
 * удаление навсегда — только отключённого, по номеру.
 *
 * Связанные строки (избранное, уведомления, резюме — cascade; объявления,
 * платежи, отзывы — null) база правит сама по внешним ключам: действия
 * по ключам выполняются от владельца таблиц, отдельные права на них
 * роли не нужны. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'UPDATE (deleted_at) ON users',
        'DELETE ON users',
    ];

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        foreach (self::GRANTS as $grant) {
            DB::statement("GRANT {$grant} TO ".self::ROLE);
        }
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        foreach (self::GRANTS as $grant) {
            DB::statement("REVOKE {$grant} FROM ".self::ROLE);
        }
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
