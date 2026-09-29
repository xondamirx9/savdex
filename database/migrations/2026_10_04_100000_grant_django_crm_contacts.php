<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Этап 6: контакты CRM переходят к Django — раздел «Контакты» в админке
 * на Python (savdex/crm). Удаление — в корзину (deleted_at), то есть
 * UPDATE; настоящего удаления у раздела нет. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT, UPDATE ON crm_contacts',
        'USAGE ON SEQUENCE crm_contacts_id_seq',
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
