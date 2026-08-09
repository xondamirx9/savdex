<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Склейка дублей стран, разошедшихся по регистру кода.
 *
 * GeoSeeder заводил страны с кодом 'uz', а DemoSeeder и фабрика
 * компаний искали 'UZ'. Уникальность в базе регистрозависима, поэтому
 * рядом появлялась вторая страна: в списке при регистрации было два
 * «Узбекистана», и выбравшие второй получали пустой список городов —
 * города висели на первом.
 *
 * Дубли переносятся на самую раннюю запись, а не удаляются вслепую:
 * на них уже ссылаются компании и города.
 */
return new class extends Migration
{
    public function up(): void
    {
        $groups = DB::table('countries')
            ->get(['id', 'code'])
            ->groupBy(fn (object $c): string => mb_strtolower(trim($c->code)))
            ->filter(fn ($group): bool => $group->count() > 1);

        foreach ($groups as $code => $group) {
            $sorted = $group->sortBy('id')->values();
            $keep = $sorted->first();
            $drop = $sorted->slice(1)->pluck('id')->all();

            DB::table('cities')->whereIn('country_id', $drop)->update(['country_id' => $keep->id]);
            DB::table('companies')->whereIn('country_id', $drop)->update(['country_id' => $keep->id]);

            // Переводы дубля не переносим: у оставшейся страны они уже
            // есть, а пара «страна + язык» уникальна
            DB::table('country_translations')->whereIn('country_id', $drop)->delete();
            DB::table('countries')->whereIn('id', $drop)->delete();
        }

        foreach (DB::table('countries')->get(['id', 'code']) as $country) {
            $normalized = mb_strtolower(trim($country->code));

            if ($normalized !== $country->code) {
                DB::table('countries')->where('id', $country->id)->update(['code' => $normalized]);
            }
        }
    }

    /**
     * Обратной операции нет: какая из склеенных записей была дублем
     * и что именно на неё ссылалось, после переноса не восстановить.
     */
    public function down(): void {}
};
