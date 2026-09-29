<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Раскрытие контактов на визитке на Django (этап 5, шаг 40): новая строка
 * раскрытия, расход лимита тарифа или кредита с записью в историю
 * кошелька, счётчик раскрытий объявления, уведомление компании.
 * Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON contact_unlocks',
        'USAGE ON SEQUENCE contact_unlocks_id_seq',
        'UPDATE (credits, contacts_used_this_period, updated_at) ON wallets',
        'INSERT ON wallet_transactions',
        'USAGE ON SEQUENCE wallet_transactions_id_seq',
        'UPDATE (unlocks_count, updated_at) ON listings',
        'UPDATE (unlocks) ON listing_stats',
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
