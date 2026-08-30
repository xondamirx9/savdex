<?php

declare(strict_types=1);

use App\Support\SearchText;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Поисковый индекс компаний — как у объявлений: название в обеих
 * графиках. «Sement Treyd» должен находиться по «цемент» и наоборот.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->text('search_text')->nullable()->after('legal_name');
        });

        DB::table('companies')
            ->select('id', 'name', 'legal_name')
            ->orderBy('id')
            ->chunkById(200, function ($rows): void {
                foreach ($rows as $row) {
                    DB::table('companies')->where('id', $row->id)->update([
                        'search_text' => SearchText::index(trim($row->name.' '.$row->legal_name)),
                    ]);
                }
            });
    }

    public function down(): void
    {
        Schema::table('companies', function (Blueprint $table): void {
            $table->dropColumn('search_text');
        });
    }
};
