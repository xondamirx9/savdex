<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права хозяина роли savdex_django на таблицы кабинета (этап 5, шаг 63).
 *
 * Отзывы, чат, контакты и файлы компании, мини-сайт, раскрытия
 * контактов, «Кто смотрел», настройки уведомлений, рассылки и прочее —
 * теперь Django (python/savdex/guards.py, OWNED_TABLES). Хозяину нужна
 * запись целиком, а не по кусочку под каждую форму. users, companies и
 * user_notifications — отдельными шагами. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const TABLES = [
        'login_attempts', 'company_attributes', 'company_category', 'company_contacts',
        'company_documents', 'company_invitations', 'company_sites', 'company_site_products',
        'reviews', 'platform_reviews', 'contact_unlocks', 'audience_views', 'message_threads',
        'messages', 'notifications', 'notification_preferences', 'broadcasts',
    ];

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        // notifications (уведомления Laravel) — ключ uuid, последовательности нет
        $sequences = array_map(
            fn (string $t): string => $t.'_id_seq',
            array_values(array_diff(self::TABLES, ['notifications'])),
        );

        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON '.implode(', ', self::TABLES).' TO '.self::ROLE);
        DB::statement('GRANT USAGE, SELECT ON SEQUENCE '.implode(', ', $sequences).' TO '.self::ROLE);
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
