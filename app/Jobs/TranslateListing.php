<?php

declare(strict_types=1);

namespace App\Jobs;

use App\Models\Listing;
use App\Services\MachineTranslator;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;

/**
 * Перевод объявления на языки каталога — фоном, после публикации.
 *
 * В очереди, а не в запросе: перевод — четыре обращения к внешнему
 * сервису, и публикация не должна их ждать. Уже готовые переводы
 * не перезапрашиваются; неудавшиеся остаются пустыми и добираются
 * ежечасной задачей (routes/console.php).
 */
class TranslateListing implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable;

    public int $tries = 3;

    public int $backoff = 30;

    public function __construct(public readonly int $listingId) {}

    public function handle(MachineTranslator $translator): void
    {
        $listing = Listing::query()->find($this->listingId);

        if ($listing === null) {
            return;
        }

        $titles = $listing->title_i18n ?? [];
        $descriptions = $listing->description_i18n ?? [];

        foreach (MachineTranslator::TARGETS as $locale) {
            $titles[$locale] ??= $translator->translate($listing->title, $locale);

            if (filled($listing->description)) {
                $descriptions[$locale] ??= $translator->translate((string) $listing->description, $locale);
            }
        }

        // array_filter убирает несложившиеся переводы: пустой ключ
        // будет запрошен заново при следующем заходе задачи
        $listing->forceFill([
            'title_i18n' => array_filter($titles),
            'description_i18n' => array_filter($descriptions),
        ])->save();
    }
}
