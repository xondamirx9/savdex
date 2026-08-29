<?php

declare(strict_types=1);

use App\Models\Listing;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Предварительная модерация объявлений отключена: публикация сразу
 * выводит на витрину, контроль остался постмодерацией. Всё, что
 * успело зависнуть в очереди «на модерации», выпускается — иначе
 * эти объявления остались бы невидимыми и в каталоге, и в кабинете:
 * вкладки «На модерации» больше нет.
 */
return new class extends Migration
{
    public function up(): void
    {
        DB::table('listings')
            ->where('status', Listing::STATUS_MODERATION)
            ->whereNull('published_at')
            ->update(['published_at' => now()]);

        DB::table('listings')
            ->where('status', Listing::STATUS_MODERATION)
            ->where(fn ($q) => $q->whereNull('expires_at')->orWhere('expires_at', '<', now()))
            ->update(['expires_at' => now()->addDays(Listing::LIFETIME_DAYS)]);

        DB::table('listings')
            ->where('status', Listing::STATUS_MODERATION)
            ->update(['status' => Listing::STATUS_ACTIVE]);
    }

    public function down(): void
    {
        // Обратной дороги нет: какие объявления стояли в очереди,
        // после выпуска уже не восстановить — и не нужно
    }
};
