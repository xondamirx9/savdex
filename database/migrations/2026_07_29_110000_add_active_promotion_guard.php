<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Одно и то же продвижение не запускается на объявлении дважды.
 *
 * Проверка была только в коде — между ней и вставкой помещался второй
 * запрос, и компания платила за продвижение, которое ничего не усиливает.
 * Теперь обещание держит база.
 *
 * Колонка active_key вместо частичного индекса: `WHERE status = 'active'`
 * поддерживают PostgreSQL и SQLite, но не MySQL, а тесты и прод должны
 * вести себя одинаково. У активной строки ключ заполнен, у завершённой —
 * null, и NULL в уникальном индексе не конфликтует ни с чем.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('promotions', function (Blueprint $table): void {
            $table->string('active_key', 64)->nullable()->after('status');
        });

        // Уже запущенные продвижения должны попасть под то же правило
        foreach (DB::table('promotions')->where('status', 'active')->get(['id', 'listing_id', 'promotion_type_id']) as $row) {
            DB::table('promotions')->where('id', $row->id)->update([
                'active_key' => $row->listing_id.':'.$row->promotion_type_id,
            ]);
        }

        /*
         * Дубли, накопившиеся до ограничения, гасим: оставляем самое
         * раннее, остальные помечаем завершёнными. Удалять нельзя —
         * за них заплачено, и списание должно остаться в истории.
         */
        $duplicates = DB::table('promotions')
            ->where('status', 'active')
            ->whereNotNull('active_key')
            ->orderBy('id')
            ->get(['id', 'active_key'])
            ->groupBy('active_key')
            ->filter(fn ($group): bool => $group->count() > 1);

        foreach ($duplicates as $group) {
            $extra = $group->slice(1)->pluck('id')->all();

            DB::table('promotions')->whereIn('id', $extra)->update([
                'status' => 'finished',
                'active_key' => null,
            ]);
        }

        Schema::table('promotions', function (Blueprint $table): void {
            $table->unique('active_key');
        });
    }

    public function down(): void
    {
        Schema::table('promotions', function (Blueprint $table): void {
            $table->dropUnique(['active_key']);
            $table->dropColumn('active_key');
        });
    }
};
