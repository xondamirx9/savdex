<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права хозяина роли savdex_django на таблицы каталога (этап 4, шаг 62).
 *
 * Хозяин объявлений, тендеров, IT-задач и резюме со статистикой и
 * избранным — теперь Django (python/savdex/guards.py, OWNED_TABLES).
 * До сих пор роль получала права по кусочку под каждую перенесённую
 * форму (где-то без UPDATE, где-то без DELETE); хозяину нужна запись
 * целиком. Роли нет (разработка, проверки) — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const TABLES = [
        'listings', 'listing_attributes', 'listing_images', 'listing_stats', 'favorites',
        'search_hits', 'tenders', 'it_tasks', 'it_task_files', 'resumes',
    ];

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        $tables = implode(', ', self::TABLES);
        $sequences = implode(', ', array_map(fn (string $t): string => $t.'_id_seq', self::TABLES));

        DB::statement("GRANT SELECT, INSERT, UPDATE, DELETE ON {$tables} TO ".self::ROLE);
        DB::statement("GRANT USAGE, SELECT ON SEQUENCE {$sequences} TO ".self::ROLE);
    }

    public function down(): void
    {
        // Отзывать нечего: права, выданные раньше по кусочку, этой
        // миграции не принадлежат, а отзыв целиком сломал бы формы
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
