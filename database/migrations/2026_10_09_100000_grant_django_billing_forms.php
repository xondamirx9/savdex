<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Формы кассы на Django (этап 7, шаг 53): отмена и включение
 * автопродления, отвязка карты, отказ от неоплаченного счёта с
 * возвратом захваченного промокода. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'UPDATE (auto_renew, cancelled_at, updated_at) ON subscriptions',
        'DELETE ON payment_methods',
        'UPDATE (status, confirmed_by, admin_note, updated_at) ON payments',
        'UPDATE (used_at, used_by_company_id, used_by_user_id, updated_at) ON promo_codes',
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
