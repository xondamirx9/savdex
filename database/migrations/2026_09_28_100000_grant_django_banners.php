<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права роли savdex_django на баннеры — они перешли к Django (этап 2
 * переноса). Картинки Django кладёт на тот же публичный диск, что и
 * Laravel. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON banners, banner_images TO '.self::ROLE);
        DB::statement('GRANT USAGE ON SEQUENCE banners_id_seq, banner_images_id_seq TO '.self::ROLE);
    }

    public function down(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        DB::statement('REVOKE INSERT, UPDATE, DELETE ON banners, banner_images FROM '.self::ROLE);
        DB::statement('REVOKE USAGE ON SEQUENCE banners_id_seq, banner_images_id_seq FROM '.self::ROLE);
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
