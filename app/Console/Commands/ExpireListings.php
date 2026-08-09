<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Models\Listing;
use App\Support\Notifier;
use Illuminate\Console\Command;

/**
 * Снятие истёкших объявлений и предупреждение о скором истечении.
 *
 * Без этой команды `expires_at` был просто датой в базе: статус
 * никогда не менялся, объявления висели в выдаче вечно, а обещание
 * «объявление действует 30 дней» не выполнялось ни в одну сторону.
 */
class ExpireListings extends Command
{
    protected $signature = 'listings:expire';

    protected $description = 'Снять истёкшие объявления и предупредить о скором истечении';

    public function handle(Notifier $notifier): int
    {
        $expired = $this->expire($notifier);
        $warned = $this->warn3DaysBefore($notifier);

        $this->info("Снято с публикации: {$expired}. Предупреждений отправлено: {$warned}.");

        return self::SUCCESS;
    }

    private function expire(Notifier $notifier): int
    {
        $listings = Listing::query()
            ->with('company')
            ->where('status', Listing::STATUS_ACTIVE)
            ->whereNotNull('expires_at')
            ->where('expires_at', '<=', now())
            ->get();

        foreach ($listings as $listing) {
            $listing->forceFill(['status' => Listing::STATUS_EXPIRED])->save();

            if ($listing->company !== null) {
                $notifier->company(
                    $listing->company,
                    'listing_expiring',
                    "Объявление «{$listing->title}» снято: истёк срок размещения",
                    [
                        'tone' => 'warning',
                        'body' => 'Продлите его в кабинете — показы возобновятся сразу.',
                        'url' => '/cabinet/listings?status='.Listing::STATUS_EXPIRED,
                    ],
                );
            }
        }

        return $listings->count();
    }

    /**
     * Предупреждение за три дня.
     *
     * Уведомление отправляется один раз: повторный запуск команды
     * на следующий день не должен слать то же самое снова, поэтому
     * окно ограничено сутками, а не «всё, что истекает в ближайшие три дня».
     */
    private function warn3DaysBefore(Notifier $notifier): int
    {
        $listings = Listing::query()
            ->with('company')
            ->where('status', Listing::STATUS_ACTIVE)
            ->whereNotNull('expires_at')
            ->whereBetween('expires_at', [now()->addDays(3), now()->addDays(4)])
            ->get();

        foreach ($listings as $listing) {
            if ($listing->company === null) {
                continue;
            }

            $notifier->company(
                $listing->company,
                'listing_expiring',
                "Объявление «{$listing->title}» истекает через 3 дня",
                [
                    'tone' => 'warning',
                    'body' => 'После истечения показы прекращаются. Продлите в один клик.',
                    'url' => '/cabinet/listings',
                ],
            );
        }

        return $listings->count();
    }
}
