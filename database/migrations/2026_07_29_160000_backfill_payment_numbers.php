<?php

declare(strict_types=1);

use App\Services\OrderService;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Номера для платежей, заведённых до появления счетов.
 *
 * Колонка number добавлялась как nullable — иначе миграция упала бы
 * на существующих строках. Заполнить их тогда забыл, и печатная форма
 * выводила «Счёт на оплату» без номера: документ без реквизита,
 * по которому его ищут в банке.
 *
 * Номер строится из id тем же правилом, что и у новых, — так он
 * остаётся уникальным и не пересекается с будущими.
 */
return new class extends Migration
{
    public function up(): void
    {
        foreach (DB::table('payments')->whereNull('number')->pluck('id') as $id) {
            DB::table('payments')
                ->where('id', $id)
                ->update(['number' => OrderService::makeNumber((int) $id)]);
        }
    }

    /**
     * Обратной операции нет: пустой номер ничем не лучше заполненного,
     * а восстанавливать «как было» — возвращать документ без реквизита.
     */
    public function down(): void {}
};
