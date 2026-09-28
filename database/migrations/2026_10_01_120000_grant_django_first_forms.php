<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Первые формы кабинета на Django (этап 5, шаг 21): прочтение
 * уведомлений, избранное (строка, счётчик объявления и дневная
 * статистика), настройки уведомлений. Только эти столбцы и строки —
 * остальное в этих таблицах пишет Laravel. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'UPDATE (read_at, updated_at) ON user_notifications',
        'INSERT, DELETE ON favorites',
        'USAGE ON SEQUENCE favorites_id_seq',
        'UPDATE (favorites_count) ON listings',
        'UPDATE (favorites) ON listing_stats',
        'INSERT, UPDATE (email, telegram, updated_at) ON notification_preferences',
        'USAGE ON SEQUENCE notification_preferences_id_seq',
    ];

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        foreach (self::GRANTS as $grant) {
            DB::statement("GRANT {$grant} TO ".self::ROLE);
        }
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        foreach (self::GRANTS as $grant) {
            DB::statement("REVOKE {$grant} FROM ".self::ROLE);
        }
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
