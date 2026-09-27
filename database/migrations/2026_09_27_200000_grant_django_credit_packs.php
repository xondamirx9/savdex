<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права роли savdex_django на пакеты контактов — они перешли к Django вслед
 * за справочниками (этап 2 переноса). Как и для стран: выдаётся при деплое
 * владельцем таблиц; роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON credit_packs TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE credit_packs_id_seq TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE INSERT, UPDATE, DELETE ON credit_packs FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE credit_packs_id_seq FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
