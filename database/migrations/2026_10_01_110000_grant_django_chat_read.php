<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Разговор в кабинете на Django (этап 5) отмечает прочитанное, как
 * MessageThread::markReadFor: время прочтения своей стороны и метка
 * обновления. Остальное в разговорах пишет Laravel. Роли нет — делать
 * нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT UPDATE (buyer_read_at, seller_read_at, updated_at) ON message_threads TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE UPDATE (buyer_read_at, seller_read_at, updated_at) ON message_threads FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
