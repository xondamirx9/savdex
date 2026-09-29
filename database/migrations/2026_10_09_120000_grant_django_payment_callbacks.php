<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Колбэки шлюза Uzum на Django (этап 7, шаг 54): транзакции Merchant API
 * и вебхука кассы, отметка счёта оплаченным и выдача купленного —
 * подписка по оплате (права — grant_django_billing_orders) или кредиты
 * в кошелёк с историей. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON payment_transactions',
        'USAGE ON SEQUENCE payment_transactions_id_seq',
        'UPDATE (payment_id, amount_minor, currency, payload, state, performed_at, cancelled_at, updated_at) ON payment_transactions',
        'UPDATE (paid_at, subscription_id, payment_method_id) ON payments',
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
