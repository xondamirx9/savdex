<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права роли savdex_django на таблицы, которые перешли к Django.
 *
 * Этап 2 переноса (docs/migration-to-python.md): справочник стран
 * правится в разделе админки на Python, и его роль в PostgreSQL должна
 * уметь писать страны с их названиями и вставлять строки в журнал
 * действий (только вставлять — журнал не правится и не удаляется).
 *
 * Выдаётся миграцией, а не руками в Shell: миграции выполняет владелец
 * таблиц при каждом деплое, и права едут вместе с кодом, которому нужны.
 * Роли нет (разработка, проверки) — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON countries, country_translations TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE countries_id_seq, country_translations_id_seq TO '.self::ROLE);
        DB::statement('GRANT INSERT ON admin_actions TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE admin_actions_id_seq TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE INSERT, UPDATE, DELETE ON countries, country_translations FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE countries_id_seq, country_translations_id_seq FROM '.self::ROLE);
        DB::statement('REVOKE INSERT ON admin_actions FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE admin_actions_id_seq FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
