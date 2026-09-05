<?php

declare(strict_types=1);

namespace App\Jobs;

use App\Models\Tender;
use App\Services\MachineTranslator;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;

/**
 * Перевод тендера на языки витрины — фоном, после публикации.
 *
 * Та же схема, что у объявлений (TranslateListing): готовые переводы
 * не перезапрашиваются, несложившиеся остаются пустыми и добираются
 * ежечасной задачей из routes/console.php.
 */
class TranslateTender implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable;

    public int $tries = 3;

    public int $backoff = 30;

    public function __construct(public readonly int $tenderId) {}

    public function handle(MachineTranslator $translator): void
    {
        $tender = Tender::query()->find($this->tenderId);

        if ($tender === null) {
            return;
        }

        $titles = $tender->title_i18n ?? [];
        $descriptions = $tender->description_i18n ?? [];

        foreach (MachineTranslator::TARGETS as $locale) {
            $titles[$locale] ??= $translator->translate($tender->title, $locale);

            if (filled($tender->description)) {
                $descriptions[$locale] ??= $translator->translate((string) $tender->description, $locale);
            }
        }

        $tender->forceFill([
            'title_i18n' => array_filter($titles),
            'description_i18n' => array_filter($descriptions),
        ])->save();
    }
}
