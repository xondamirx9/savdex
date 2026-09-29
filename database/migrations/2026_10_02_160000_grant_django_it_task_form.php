<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * IT-задача на Django (этап 5, шаг 43): новая задача и правка, файлы
 * к задаче. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON it_tasks',
        'USAGE ON SEQUENCE it_tasks_id_seq',
        'UPDATE (slug, title, description, service_type, stack, budget_type, budget_from, budget_to, currency, deadline_at) ON it_tasks',
        'INSERT ON it_task_files',
        'USAGE ON SEQUENCE it_task_files_id_seq',
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
