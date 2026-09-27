<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Страницы сайта на Django (этап 3 переноса) ставят непереведённый
 * текст в очередь машинного перевода — как ContentTranslation у
 * Laravel. Только добавление строк; переводит по-прежнему задача
 * Laravel translations:fill. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT SELECT, INSERT ON content_translations TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE content_translations_id_seq TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE INSERT ON content_translations FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE content_translations_id_seq FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
