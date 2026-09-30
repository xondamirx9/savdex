<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права хозяина роли savdex_django на колокольчик (этап 5, шаг 65).
 *
 * Просьбы оставить отзыв переехали в Django (python/savdex/schedule.py),
 * и хозяин user_notifications теперь Django (OWNED_TABLES). Денежное
 * расписание Laravel ещё добавляет сюда строки — до передачи денег.
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

        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON user_notifications TO '.self::ROLE);
        DB::statement('GRANT USAGE, SELECT ON SEQUENCE user_notifications_id_seq TO '.self::ROLE);
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
