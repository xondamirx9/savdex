<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Госзакупки: признак у закупки. Загружает их файлом раздел «Закупки»
 * в админке Django (python/savdex/tenders), на сайте у такой закупки —
 * значок «Госзакупка». Роль Django получает запись в таблицу целиком:
 * раздел заводит, правит и удаляет закупки сам.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    public function up(): void
    {
        Schema::table('tenders', function (Blueprint $table): void {
            $table->boolean('is_government')->default(false)->after('customer');
        });

        if ($this->roleExists()) {
            DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON tenders TO '.self::ROLE);
            DB::statement('GRANT USAGE ON SEQUENCE tenders_id_seq TO '.self::ROLE);
        }
    }

    public function down(): void
    {
        Schema::table('tenders', function (Blueprint $table): void {
            $table->dropColumn('is_government');
        });
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
