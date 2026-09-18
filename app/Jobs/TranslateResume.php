<?php

declare(strict_types=1);

namespace App\Jobs;

use App\Models\Resume;
use App\Services\MachineTranslator;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;

/**
 * Перевод резюме на языки площадки — фоном, после публикации.
 *
 * В очереди, а не в запросе: переводится должность, текст о себе
 * и места работы, и человек, нажавший «Опубликовать», не должен
 * ждать десяток обращений к переводчику. Готовые переводы
 * не перезапрашиваются, несложившиеся добираются ежечасной задачей.
 */
class TranslateResume implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable;

    public int $tries = 3;

    public int $backoff = 30;

    /**
     * Сколько мест работы переводим.
     *
     * Первые места — те, что человек считает главными, и именно их
     * читает работодатель. Двадцать мест на четыре языка — это сто
     * шестьдесят обращений к переводчику ради строк, до которых
     * не долистывают.
     */
    private const JOBS_LIMIT = 8;

    public function __construct(public readonly int $resumeId) {}

    public function handle(MachineTranslator $translator): void
    {
        $resume = Resume::query()->find($this->resumeId);

        if ($resume === null) {
            return;
        }

        $titles = $resume->title_i18n ?? [];
        $abouts = $resume->about_i18n ?? [];
        $jobs = $resume->jobs_i18n ?? [];
        $original = $resume->jobs ?? [];

        foreach (MachineTranslator::TARGETS as $locale) {
            $titles[$locale] ??= $translator->translate($resume->title, $locale);

            if (filled($resume->about)) {
                $abouts[$locale] ??= $translator->translate((string) $resume->about, $locale);
            }

            if ($original !== [] && ! isset($jobs[$locale])) {
                $jobs[$locale] = $this->jobs($translator, $original, $locale);
            }
        }

        /*
         * Перечитать перед записью: пока шли обращения к переводчику,
         * человек мог поправить резюме — и его правка главнее снимка,
         * с которым задача начиналась. Список мест работы связан
         * с оригиналом порядком, поэтому при изменившемся числе мест
         * перевод не сохраняем: он относится уже к другому резюме.
         */
        $fresh = Resume::query()->find($this->resumeId);

        if ($fresh === null) {
            return;
        }

        $keepJobs = count($fresh->jobs ?? []) === count($original);

        $fresh->forceFill([
            'title_i18n' => array_filter(($fresh->title_i18n ?? []) + $titles),
            'about_i18n' => array_filter(($fresh->about_i18n ?? []) + $abouts),
            'jobs_i18n' => $keepJobs ? array_filter(($fresh->jobs_i18n ?? []) + $jobs) : $fresh->jobs_i18n,
        ])->saveQuietly();
    }

    /**
     * Должности и обязанности одного языка — в том же порядке,
     * что в оригинале: по нему они и связаны.
     *
     * @param  list<array<string, mixed>>  $jobs
     * @return list<array{position: string|null, duties: string|null}>
     */
    private function jobs(MachineTranslator $translator, array $jobs, string $locale): array
    {
        $rows = [];

        foreach ($jobs as $i => $job) {
            $translate = $i < self::JOBS_LIMIT;

            $rows[] = [
                'position' => $translate && filled($job['position'] ?? null)
                    ? $translator->translate((string) $job['position'], $locale)
                    : null,
                'duties' => $translate && filled($job['duties'] ?? null)
                    ? $translator->translate((string) $job['duties'], $locale)
                    : null,
            ];
        }

        return $rows;
    }
}
