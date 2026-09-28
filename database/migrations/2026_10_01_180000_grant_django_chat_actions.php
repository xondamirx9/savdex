<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Чат на Django (этап 5, шаг 26): сообщение в разговор, отклик на
 * объявление и IT-задачу — новый разговор, списание отклика из квоты
 * тарифа (кошелёк заводится, если его не было), счётчик откликов задачи,
 * уведомление собеседника. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON messages',
        'USAGE ON SEQUENCE messages_id_seq',
        'INSERT ON message_threads',
        'USAGE ON SEQUENCE message_threads_id_seq',
        'UPDATE (last_message_at, buyer_read_at, seller_read_at, updated_at) ON message_threads',
        'INSERT ON wallets',
        'USAGE ON SEQUENCE wallets_id_seq',
        'UPDATE (responses_used_this_period, updated_at) ON wallets',
        'UPDATE (responses_count, updated_at) ON it_tasks',
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
