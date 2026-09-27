<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Каталог объявлений на Django (этап 4 переноса) считает показы и
 * поисковые запросы — как StatsRecorder у Laravel: счётчик в listings,
 * дневные строки listing_stats и search_hits. Только добавление строк
 * и правка счётчиков; остальное в этих таблицах пишет Laravel.
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

        DB::statement('GRANT SELECT ON listings TO '.self::ROLE);
        DB::statement('GRANT UPDATE (impressions_count, updated_at) ON listings TO '.self::ROLE);

        DB::statement('GRANT SELECT, INSERT ON listing_stats TO '.self::ROLE);
        DB::statement('GRANT UPDATE (impressions, views, updated_at) ON listing_stats TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE listing_stats_id_seq TO '.self::ROLE);

        DB::statement('GRANT SELECT, INSERT ON search_hits TO '.self::ROLE);
        DB::statement('GRANT UPDATE (impressions, updated_at) ON search_hits TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE search_hits_id_seq TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE UPDATE (impressions_count, updated_at) ON listings FROM '.self::ROLE);
        DB::statement('REVOKE INSERT, UPDATE ON listing_stats FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE listing_stats_id_seq FROM '.self::ROLE);
        DB::statement('REVOKE INSERT, UPDATE ON search_hits FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE search_hits_id_seq FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
