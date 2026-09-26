<?php

declare(strict_types=1);

use App\Support\Business;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Сроки уже заведённых баннеров — на ташкентское время.
 *
 * До исправления форма админки понимала введённое время как UTC:
 * «16:00» по часам администратора ложилось в базу как 16:00 UTC, то есть
 * 21:00 в Ташкенте. Исправление формы (AppServiceProvider::
 * configureAdminTimezone) действует только на новые правки, а у старых
 * баннеров срок так и остался бы сдвинутым на пять часов — и форма
 * честно показывала бы этот неверный срок.
 *
 * Сдвигать можно все строки подряд, потому что у дат баннера один
 * писатель — форма админки: сидеров и импорта для баннеров нет. Для
 * срока объявления или дедлайна тендера так нельзя — их ставит и код
 * площадки, уже правильно, и слепой сдвиг испортил бы верные значения.
 *
 * Через DB::table, а не модель: это исправление данных, а не действие
 * администратора, и в журнал действий оно попадать не должно.
 */
return new class extends Migration
{
    public function up(): void
    {
        // Записанное — время по Ташкенту, выданное за UTC. Прочитать
        // его как ташкентское и перевести в настоящий UTC
        $this->shift(fn (string $raw): Carbon => Carbon::parse($raw, Business::timezone())->utc());
    }

    public function down(): void
    {
        $this->shift(fn (string $raw): Carbon => Carbon::parse($raw, 'UTC')->setTimezone(Business::timezone()));
    }

    /** @param  Closure(string): Carbon  $convert */
    private function shift(Closure $convert): void
    {
        $rows = DB::table('banners')->select(['id', 'starts_at', 'ends_at'])->get();

        foreach ($rows as $row) {
            $changes = [];

            foreach (['starts_at', 'ends_at'] as $column) {
                if ($row->{$column} !== null) {
                    $changes[$column] = $convert((string) $row->{$column})->format('Y-m-d H:i:s');
                }
            }

            if ($changes !== []) {
                DB::table('banners')->where('id', $row->id)->update($changes);
            }
        }
    }
};
