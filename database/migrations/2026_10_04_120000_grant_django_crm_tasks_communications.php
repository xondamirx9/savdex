<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Этап 6: задачи и коммуникации CRM переходят к Django — разделы
 * «Задачи» и «Коммуникации» в админке на Python (savdex/crm). Задача
 * удаляется в корзину (deleted_at, то есть UPDATE), запись разговора —
 * насовсем (DELETE: мягкого удаления у неё нет). Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT, UPDATE ON crm_tasks',
        'USAGE ON SEQUENCE crm_tasks_id_seq',
        'INSERT, UPDATE, DELETE ON crm_communications',
        'USAGE ON SEQUENCE crm_communications_id_seq',
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
