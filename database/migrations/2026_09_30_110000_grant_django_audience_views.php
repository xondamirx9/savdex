<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Визитка компании на Django (этап 4 переноса) пишет «Кто мной
 * интересуется» — как StatsRecorder::companyView у Laravel: строку
 * в audience_views. Только вставка; читает раздел кабинет Laravel.
 * Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT SELECT, INSERT ON audience_views TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE audience_views_id_seq TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE INSERT ON audience_views FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE audience_views_id_seq FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
