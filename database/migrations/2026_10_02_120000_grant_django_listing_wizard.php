<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Мастер объявления на Django (этап 5, шаги 38–39): новый черновик,
 * автосохранение (поля, характеристики, теги) и публикация. Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON listings',
        'USAGE ON SEQUENCE listings_id_seq',
        'INSERT, UPDATE, DELETE ON listing_attributes',
        'USAGE ON SEQUENCE listing_attributes_id_seq',
        'UPDATE (type, tags, category_id, title, description, price, bundle_price, currency, unit, price_negotiable, min_order, delivery_terms, payment_terms, wizard_step, slug) ON listings',
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
