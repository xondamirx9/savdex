<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Этап 6: модерация и данные в админке на Python (savdex/moderation,
 * savdex/data, savdex/tenders) вместо разделов Filament.
 *
 * - отзывы о компаниях: правка формой, решения модератора, удаление
 *   насовсем (SoftDeletes нет) — UPDATE и DELETE целиком;
 * - отзывы о площадке: решение — статус, формулировка, кто и когда
 *   (столбцы выданы на этапе 5 вместе с «Оцените SavdEx»);
 * - документы на проверку: решение — статус, причина, кто и когда;
 * - резюме: снятие с причиной — moderation_note (остальное выдано на
 *   этапе 5);
 * - IT-задачи: правка формой — UPDATE целиком.
 *
 * Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'UPDATE, DELETE ON reviews',
        'UPDATE (moderation_status, moderation_note, moderated_by, moderated_at, updated_at) ON company_documents',
        'UPDATE (moderation_note) ON resumes',
        'UPDATE ON it_tasks',
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
