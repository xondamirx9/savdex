<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Этап 6, продолжение: объявления, компании, рассылки и пользователи в
 * админке на Python (savdex/data, savdex/system, savdex/accounts) вместо
 * разделов Filament.
 *
 * - объявления: правка формой, решения, корзина и удаление насовсем
 *   (связанное база удаляет сама), загрузка книгами Excel — UPDATE и
 *   DELETE целиком; фото — порядок и удаление (вставка выдана на этапе 5);
 * - компании: правка формой, решения (уровень, партнёрство, логотип,
 *   эмблема, блокировка), загрузка таблицей, корзина и удаление насовсем —
 *   UPDATE и DELETE целиком;
 * - рассылки: черновик, правка, отправка, удаление;
 * - пользователи: правка формой, «Роли и права» — почта, доступ в панель,
 *   роль, статус, личные права (остальные столбцы выданы на этапе 5).
 *
 * Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'UPDATE, DELETE ON listings',
        'UPDATE (sort, updated_at), DELETE ON listing_images',
        'UPDATE, DELETE ON companies',
        'INSERT, UPDATE, DELETE ON broadcasts',
        'USAGE ON SEQUENCE broadcasts_id_seq',
        'UPDATE (email, is_admin, admin_role, status, admin_permissions) ON users',
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
