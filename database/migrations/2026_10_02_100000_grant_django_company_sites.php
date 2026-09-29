<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Мини-сайт своей компании на Django (этап 5, шаг 35): адрес и оформление
 * черновика, публикация и снятие, фон первого экрана; товары (шаг 36).
 * Роли нет — делать нечего.
 */
return new class extends Migration
{
    private const ROLE = 'savdex_django';

    private const GRANTS = [
        'INSERT ON company_sites',
        'USAGE ON SEQUENCE company_sites_id_seq',
        'UPDATE (subdomain, status, theme, published_theme, published_at, updated_at) ON company_sites',
        'INSERT ON company_site_products',
        'USAGE ON SEQUENCE company_site_products_id_seq',
        'UPDATE (title, description, price, currency, unit, image_path, thumb_path, updated_at) ON company_site_products',
        'DELETE ON company_site_products',
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
