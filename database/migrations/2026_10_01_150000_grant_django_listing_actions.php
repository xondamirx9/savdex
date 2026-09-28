<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * «Мои объявления» на Django (этап 5, шаг 23): продление, снятие,
 * повторная публикация, удаление — статус, сроки, пометка модератора,
 * мягкое удаление и search_text; уведомление компании о повторной
 * публикации — лента кабинета и колокольчик. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'UPDATE (status, expires_at, published_at, moderation_note, deleted_at, search_text, updated_at) ON listings',
        'INSERT ON activity_events',
        'USAGE ON SEQUENCE activity_events_id_seq',
        'INSERT ON user_notifications',
        'USAGE ON SEQUENCE user_notifications_id_seq',
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
