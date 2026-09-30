<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права хозяина роли savdex_django на компании (этап 5, шаг 64).
 *
 * Последний живой писатель Laravel в companies — ежедневный пересчёт
 * рейтингов — переехал в Django (python/savdex/schedule.py), и хозяин
 * таблицы теперь Django (OWNED_TABLES). До сих пор роль получала права
 * по столбцам под каждую форму; хозяину нужна запись целиком. Роли нет —
 * делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON companies TO '.self::ROLE);
        DB::statement('GRANT USAGE, SELECT ON SEQUENCE companies_id_seq TO '.self::ROLE);
    }

    public function down(): void
    {
        // Отзывать нечего: права, выданные раньше по столбцам, этой
        // миграции не принадлежат, а отзыв целиком сломал бы формы
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
