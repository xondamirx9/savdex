<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права роли savdex_django на тарифы — они перешли к Django (этап 2
 * переноса). Цены и лимиты задаёт админка, PlanSeeder досоздаёт
 * только недостающие. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON plans TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE plans_id_seq TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE INSERT, UPDATE, DELETE ON plans FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE plans_id_seq FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
