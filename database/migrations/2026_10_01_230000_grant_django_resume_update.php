<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Правка своего резюме на Django (этап 5, шаг 32): новое резюме и правка
 * полей формы, опыт, адрес, сброс переводов правленого. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON resumes',
        'USAGE ON SEQUENCE resumes_id_seq',
        'UPDATE (slug, title, field, country_id, city_id, salary, currency, employment, schedule, experience_months, about, skills, jobs, education, languages, contact_name, contact_phone, contact_email, show_phone, show_email, title_i18n, about_i18n, jobs_i18n, updated_at) ON resumes',
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
