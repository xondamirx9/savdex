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
 * Раньше загруженные отличались только тем, что автор — админ; по
 * этому признаку они и помечаются задним числом.
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

        DB::table('listings')
            ->whereIn('user_id', DB::table('users')->where('is_admin', true)->select('id'))
            ->update(['source' => 'import']);
    }

    public function down(): void
    {
        Schema::table('listings', function (Blueprint $table): void {
            $table->dropColumn(['source', 'delivery_terms_i18n', 'payment_terms_i18n']);
        });
    }
};
