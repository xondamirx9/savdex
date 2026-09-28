<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Страницы сайта на Django ведут сессию Laravel (этап 5 переноса):
 * продлевают её, стирают одноразовые сообщения, заводят сессию гостю,
 * а вход по «запомнить меня» переносит её на новый номер — удаляя
 * старую строку, как Store::migrate(true).
 *
 * И язык из префикса адреса — в профиль, как SetLocale: только
 * users.locale и метка обновления. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON sessions TO '.self::ROLE);
        DB::statement('GRANT UPDATE (locale, updated_at) ON users TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE INSERT, UPDATE, DELETE ON sessions FROM '.self::ROLE);
        DB::statement('REVOKE UPDATE (locale) ON users FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
