<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Данные компании в настройках на Django (этап 5, шаг 51): метка смены
 * заполненных сведений и обращение владельца в поддержку. Остальные поля
 * компании роль уже правит (grant_django_company_profile). Роли нет —
 * делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'UPDATE (profile_changed_at) ON companies',
        'INSERT ON support_tickets',
        'USAGE ON SEQUENCE support_tickets_id_seq',
        'INSERT ON support_messages',
        'USAGE ON SEQUENCE support_messages_id_seq',
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
