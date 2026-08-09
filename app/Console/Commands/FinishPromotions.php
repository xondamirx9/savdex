<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Models\Promotion;
use Illuminate\Console\Command;

/**
 * Завершение продвижений с истёкшим сроком.
 *
 * Критично не только для честности расчёта эффекта. Места у «ТОП
 * категории» (3) и «ТОП главной» (6) ограничены, и статус `active`
 * держит слот занятым. Без этой команды после первых шести покупок
 * «ТОП главной» никто больше не смог бы его купить никогда.
 */
class FinishPromotions extends Command
{
    protected $signature = 'promotions:finish';

    protected $description = 'Завершить продвижения с истёкшим сроком и посчитать эффект';

    public function handle(): int
    {
        $promotions = Promotion::query()
            ->with('listing')
            ->where('status', 'active')
            ->whereNotNull('ends_at')
            ->where('ends_at', '<=', now())
            ->get();

        foreach ($promotions as $promotion) {
            $promotion->forceFill([
                'status' => 'finished',
                // Показы на момент завершения: разница с impressions_before
                // и есть честный эффект инструмента за период размещения
                'impressions_after' => $promotion->listing?->impressions_count ?? $promotion->impressions_before,
            ])->save();
        }

        $this->info("Завершено продвижений: {$promotions->count()}.");

        return self::SUCCESS;
    }
}
