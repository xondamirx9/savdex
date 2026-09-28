<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Профиль своей компании на Django (этап 5, шаг 33): правка полей формы и
 * search_text, новая компания и её владелец. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON companies',
        'USAGE ON SEQUENCE companies_id_seq',
        'UPDATE (name, legal_name, tin, country_id, city_id, address, description, website, founded_year, employees_range, type, custom_category, primary_role, is_it_provider, it_specializations, search_text, updated_at) ON companies',
        'UPDATE (company_id, company_role) ON users',
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
