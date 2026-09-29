<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Заказ, промокод и оплата счёта онлайн на Django (этап 7, шаг 53,
 * часть 2): новый счёт (номер, провайдер и заказ Uzum), активация
 * промокода (код — к выданной подписке), бесплатный период — новая
 * подписка, прежние истекают, кошелёк на период. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON payments',
        'USAGE ON SEQUENCE payments_id_seq',
        'UPDATE (number, provider, external_id) ON payments',
        'INSERT ON subscriptions',
        'USAGE ON SEQUENCE subscriptions_id_seq',
        'UPDATE (status) ON subscriptions',
        'UPDATE (subscription_id) ON promo_codes',
        'UPDATE (period_resets_at) ON wallets',
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
