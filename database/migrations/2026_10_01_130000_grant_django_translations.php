<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Машинный перевод на Python (этап 5, шаг 22): задачи перевода пишут
 * переводы и пересчитанный search_text, очередь текстов страниц —
 * перевод и число попыток. Только эти столбцы. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'UPDATE (title_i18n, description_i18n, search_text, updated_at) ON listings',
        'UPDATE (title_i18n, about_i18n, jobs_i18n, updated_at) ON resumes',
        'UPDATE (title_i18n, description_i18n, search_text, updated_at) ON tenders',
        'UPDATE (translation, attempts, updated_at) ON content_translations',
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
