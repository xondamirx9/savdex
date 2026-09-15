<?php

declare(strict_types=1);

namespace App\Jobs;

use App\Models\NewsPost;
use App\Services\MachineTranslator;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;

/**
 * Перевод новости на языки витрины — фоном, после публикации.
 *
 * Та же схема, что у объявлений и тендеров: готовые переводы не
 * перезапрашиваются, несложившиеся остаются пустыми и добираются
 * ежечасной задачей из routes/console.php.
 *
 * Текст новости переводится целиком, одним куском: переводить по
 * абзацам дешевле по объёму запроса, но переводчик теряет связь
 * между предложениями, и текст рассыпается.
 */
class TranslateNewsPost implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable;

    public int $tries = 3;

    public int $backoff = 30;

    public function __construct(public readonly int $postId) {}

    public function handle(MachineTranslator $translator): void
    {
        $post = NewsPost::query()->find($this->postId);

        if ($post === null) {
            return;
        }

        $titles = $post->title_i18n ?? [];
        $excerpts = $post->excerpt_i18n ?? [];
        $bodies = $post->body_i18n ?? [];

        foreach (MachineTranslator::TARGETS as $locale) {
            $titles[$locale] ??= $translator->translate($post->title, $locale);

            if (filled($post->excerpt)) {
                $excerpts[$locale] ??= $translator->translate((string) $post->excerpt, $locale);
            }

            if (filled($post->body)) {
                $bodies[$locale] ??= $translator->translate((string) $post->body, $locale);
            }
        }

        $post->forceFill([
            'title_i18n' => array_filter($titles),
            'excerpt_i18n' => array_filter($excerpts),
            'body_i18n' => array_filter($bodies),
        ])->saveQuietly();
    }
}
