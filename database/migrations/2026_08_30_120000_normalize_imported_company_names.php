<?php

declare(strict_types=1);

use App\Support\CompanyNameStyle;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Приборка после импорта из госреестра: названия капсом приводятся
 * к «Каждое Слово С Заглавной», а тип «trading» — к справочному
 * ключу trader (на карточках он показывался сырым словом вместо
 * «Торговая компания»). Названия со смешанным регистром не трогаются.
 */
return new class extends Migration
{
    public function up(): void
    {
        DB::table('companies')->where('type', 'trading')->update(['type' => 'trader']);

        DB::table('companies')
            ->select('id', 'name')
            ->orderBy('id')
            ->each(function (object $row): void {
                $humanized = CompanyNameStyle::humanize((string) $row->name);

                if ($humanized !== $row->name) {
                    DB::table('companies')->where('id', $row->id)->update(['name' => $humanized]);
                }
            });
    }

    public function down(): void
    {
        // Прежний капс не восстановить — и незачем
    }
};
