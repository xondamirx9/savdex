<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права роли savdex_django на блоки главной — они перешли
 * к Django (этап 2 переноса). Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const TABLES = ['landing_blocks'];

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        foreach (self::TABLES as $table) {
            DB::statement("GRANT SELECT, INSERT, UPDATE, DELETE ON {$table} TO ".self::ROLE);
            DB::statement("GRANT USAGE ON SEQUENCE {$table}_id_seq TO ".self::ROLE);
        }
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        foreach (self::TABLES as $table) {
            DB::statement("REVOKE INSERT, UPDATE, DELETE ON {$table} FROM ".self::ROLE);
            DB::statement("REVOKE USAGE ON SEQUENCE {$table}_id_seq FROM ".self::ROLE);
        }
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
