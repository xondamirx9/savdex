<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Разделы денег в админке Django (этап 7, шаги 56–57): выпуск промокодов
 * пачкой и их выключатель. Подписки (назначить, сменить, отменить) и
 * счета (деньги пришли, отменить) идут через права, выданные раньше
 * (grant_django_billing_forms, _billing_orders, _payment_callbacks).
 * Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON promo_codes',
        'USAGE ON SEQUENCE promo_codes_id_seq',
        'UPDATE (is_active) ON promo_codes',
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
