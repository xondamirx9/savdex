<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Страница объявления на Django (этап 4 переноса) считает просмотры —
 * как StatsRecorder::view у Laravel: +1 к listings.views_count. Право на
 * правку только этого счётчика; дневные строки и «Кто мной
 * интересуется» уже разрешены предыдущими миграциями. Роли нет —
 * делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT UPDATE (views_count) ON listings TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE UPDATE (views_count) ON listings FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
