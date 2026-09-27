<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Страница закупки на Django (этап 4 переноса) считает просмотры —
 * как $tender->increment('views_count') у Laravel. Право на правку
 * только двух столбцов: сам счётчик и метка обновления; остальное
 * в тендерах по-прежнему пишет только Laravel. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT SELECT ON tenders TO '.self::ROLE);
        DB::statement('GRANT UPDATE (views_count, updated_at) ON tenders TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE UPDATE (views_count, updated_at) ON tenders FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
