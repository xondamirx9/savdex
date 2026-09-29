<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Второй шаг регистрации, «Оцените SavdEx» и удаление учётки на Django
 * (этап 5, шаг 47): новая компания с формой собственности и её
 * направления, отзыв о площадке (новый и правка). Удаление учётки
 * обходится уже выданными правами (deleted_at у users, status у
 * listings). Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON company_category',
        'USAGE ON SEQUENCE company_category_id_seq',
        'SELECT, INSERT ON platform_reviews',
        'UPDATE (company_id, rating, rating_usability, rating_search, rating_support, body, status, screening_flags, moderator_note, moderated_by, moderated_at, updated_at) ON platform_reviews',
        'USAGE ON SEQUENCE platform_reviews_id_seq',
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
