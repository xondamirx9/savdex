<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Права хозяина роли savdex_django на пользователей и деньги (шаги 70, 72).
 *
 * Последние живые писатели Laravel перенесены в Django: смена языка ?hl=
 * и регистрация по коду (users), продвижения и расчётные периоды
 * (promotions:finish, billing:reset-periods — python/savdex/schedule.py).
 * Хозяин этих таблиц теперь Django (OWNED_TABLES). Справочники деплоя
 * (шаг 73) заводит manage.py seed — поля категорий и типы продвижения
 * тоже переходят к Django. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    /** Таблицы со своим счётчиком номеров */
    private const TABLES = [
        'users',
        'wallets',
        'wallet_transactions',
        'promotions',
        'subscriptions',
        'payment_methods',
        'payments',
        'payment_transactions',
        'promo_codes',
        'refunds',
        'category_fields',
        'promotion_types',
    ];

    public function up(): void
    {
        if (! $this->roleExists()) {
            return;
        }

        foreach (self::TABLES as $table) {
            DB::statement("GRANT SELECT, INSERT, UPDATE, DELETE ON {$table} TO ".self::ROLE);
            DB::statement("GRANT USAGE, SELECT ON SEQUENCE {$table}_id_seq TO ".self::ROLE);
        }

        // Ссылки «забыли пароль»: ключ — почта, счётчика нет
        DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO '.self::ROLE);
    }

    public function down(): void
    {
        // Отзывать нечего: права, выданные раньше по кусочку, этой
        // миграции не принадлежат, а отзыв целиком сломал бы формы
    }

    private function roleExists(): bool
    {
        return DB::getDriverName() === 'pgsql'
            && DB::scalar('select count(*) from pg_roles where rolname = ?', [self::ROLE]) > 0;
    }
};
