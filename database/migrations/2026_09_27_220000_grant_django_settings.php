<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права роли savdex_django на настройки площадки — они перешли к Django
 * (этап 2 переноса). Плюс удаление строк кэша: после правки Django сам
 * сбрасывает кэш настроек (python/savdex/laravel_cache.py). На боевом
 * кэш лежит в файлах, и таблица cache не нужна; право — для окружений
 * с CACHE_STORE=database.
 *
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

        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON settings TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE settings_id_seq TO '.self::ROLE);
        DB::statement('GRANT DELETE ON cache TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE INSERT, UPDATE, DELETE ON settings FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE settings_id_seq FROM '.self::ROLE);
        DB::statement('REVOKE DELETE ON cache FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
