<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Этап 6: лиды и сделки CRM переходят к Django — разделы «Лиды» и
 * «Сделки» в админке на Python (savdex/crm), вместе: «В сделку» пишет в
 * обе таблицы. Удаление — в корзину (deleted_at), то есть UPDATE.
 * Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT, UPDATE ON crm_leads',
        'USAGE ON SEQUENCE crm_leads_id_seq',
        'INSERT, UPDATE ON crm_deals',
        'USAGE ON SEQUENCE crm_deals_id_seq',
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
