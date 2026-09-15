<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Откуда объявление и переводы условий.
 *
 * Источник нужен витрине: объявления, загруженные админом из Excel,
 * на языке без перевода не показываются, а написанные в кабинете
 * показываются по-русски — у них перевода не было и не могло быть.
 * Раньше загруженные отличались только тем, что автор — админ, а
 * объявление принадлежит чужой компании; по этому признаку они и
 * помечаются задним числом. Просто «автор — админ» не годится:
 * человек мог написать объявления в кабинете своей компании и лишь
 * потом получить доступ в админку.
 *
 * Условия поставки и оплаты получают такие же JSON-колонки переводов,
 * как заголовок и описание: {en: ..., uz: ..., tr: ..., zh: ...}.
 * Сами колонки условий были varchar(255), а форма разрешала 500
 * символов — текст длиннее просто не помещался.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->string('source', 16)->default('cabinet')->after('user_id');
            $table->json('delivery_terms_i18n')->nullable()->after('delivery_terms');
            $table->json('payment_terms_i18n')->nullable()->after('payment_terms');
        });

        Schema::table('listings', function (Blueprint $table): void {
            $table->text('delivery_terms')->nullable()->change();
            $table->text('payment_terms')->nullable()->change();
        });

        $imported = DB::table('listings')
            ->join('users', 'users.id', '=', 'listings.user_id')
            ->where('users.is_admin', true)
            ->where(fn ($q) => $q
                ->whereNull('users.company_id')
                ->orWhereColumn('listings.company_id', '!=', 'users.company_id'))
            ->pluck('listings.id');

        DB::table('listings')->whereIn('id', $imported)->update(['source' => 'import']);
    }

    public function down(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->dropColumn(['source', 'delivery_terms_i18n', 'payment_terms_i18n']);
        });
    }
};
