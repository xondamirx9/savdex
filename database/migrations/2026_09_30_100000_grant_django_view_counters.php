<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Страницы закупки, резюме и IT-задачи на Django (этап 4 переноса)
 * считают просмотры — как $model->increment('views_count') у Laravel.
 * Право на правку только двух столбцов: сам счётчик и метка
 * обновления; остальное в этих таблицах по-прежнему пишет только
 * Laravel. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const TABLES = ['tenders', 'resumes', 'it_tasks'];

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        foreach (self::TABLES as $table) {
            DB::statement("GRANT SELECT ON {$table} TO ".self::ROLE);
            DB::statement("GRANT UPDATE (views_count, updated_at) ON {$table} TO ".self::ROLE);
        }
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        foreach (self::TABLES as $table) {
            DB::statement("REVOKE UPDATE (views_count, updated_at) ON {$table} FROM ".self::ROLE);
        }
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
