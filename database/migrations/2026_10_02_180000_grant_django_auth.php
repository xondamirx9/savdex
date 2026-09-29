<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Вход, выход, регистрация, пароль и почта на Django (этап 5, шаги 45–46):
 * новая учётка, пароль и «запомнить меня», метка последнего входа,
 * подтверждение почты, мягкое удаление учётки, счётчик неудачных входов,
 * токены сброса пароля. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON users',
        'USAGE ON SEQUENCE users_id_seq',
        'UPDATE (password, remember_token, must_change_password, last_login_at, last_login_ip, email_verified_at, deleted_at, updated_at) ON users',
        'INSERT, DELETE ON login_attempts',
        'USAGE ON SEQUENCE login_attempts_id_seq',
        'SELECT, INSERT, DELETE ON password_reset_tokens',
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
