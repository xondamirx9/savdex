<?php

declare(strict_types=1);

namespace App\Support;

use App\Services\MachineTranslator;
use Illuminate\Support\Facades\DB;
use Throwable;

/**
 * Перевод текста из базы, у которого нет своих полей под языки.
 *
 * Страница просит перевод и сразу получает ответ: готовый — если он
 * уже есть, оригинал — если нет. Недостающий текст записывается в
 * очередь (таблица content_translations) и переводится фоном задачей
 * translations:fill, так что открытие страницы никогда не ждёт
 * внешнего переводчика. К следующему заходу перевод уже на месте.
 *
 * Русская версия всегда показывает оригинал: тексты на площадке
 * пишутся по-русски.
 */
class ContentTranslation
{
    /** @var array<string, string|null> «язык|хеш» → перевод (null — ещё нет) */
    private array $memo = [];

    /** Перевод на язык посетителя или оригинал, пока перевода нет. */
    public static function text(?string $text, ?string $locale = null): ?string
    {
        return app(self::class)->get($text, $locale);
    }

    /**
     * Абзацы переведённого текста — для страниц, которые выводят
     * текст через <p>.
     *
     * @return list<string>
     */
    public static function paragraphs(?string $text, ?string $locale = null): array
    {
        $translated = trim((string) self::text($text, $locale));

        if ($translated === '') {
            return [];
        }

        return array_values(array_filter(
            array_map('trim', preg_split('/\R{2,}/u', $translated) ?: []),
            fn (string $p): bool => $p !== '',
        ));
    }

    public function get(?string $text, ?string $locale = null): ?string
    {
        $locale ??= app()->getLocale();

        if (! $this->translatable($text, $locale)) {
            return $text;
        }

        $source = trim((string) $text);
        $hash = sha1($source);
        $key = $locale.'|'.$hash;

        if (! array_key_exists($key, $this->memo)) {
            $this->memo[$key] = $this->lookup($hash, $locale, $source);
        }

        return $this->memo[$key] ?? $text;
    }

    /**
     * Загрузить переводы списка текстов одним запросом — для лент,
     * где иначе на каждую карточку уходил бы отдельный запрос.
     *
     * @param  iterable<string|null>  $texts
     */
    public function prefetch(iterable $texts, ?string $locale = null): void
    {
        $locale ??= app()->getLocale();
        $wanted = [];

        foreach ($texts as $text) {
            if ($this->translatable($text, $locale)) {
                $source = trim((string) $text);
                $hash = sha1($source);

                if (! array_key_exists($locale.'|'.$hash, $this->memo)) {
                    $wanted[$hash] = $source;
                }
            }
        }

        if ($wanted === []) {
            return;
        }

        try {
            $found = DB::table('content_translations')
                ->where('locale', $locale)
                ->whereIn('hash', array_keys($wanted))
                ->pluck('translation', 'hash');
        } catch (Throwable) {
            return;
        }

        foreach ($wanted as $hash => $source) {
            if ($found->has($hash)) {
                $this->memo[$locale.'|'.$hash] = $found[$hash];
            }
        }
    }

    private function translatable(?string $text, string $locale): bool
    {
        return $locale !== 'ru'
            && in_array($locale, MachineTranslator::TARGETS, true)
            && trim((string) $text) !== ''
            // Цифры, артикулы, размеры — переводить нечего
            && preg_match('/\p{L}{2,}/u', (string) $text) === 1;
    }

    private function lookup(string $hash, string $locale, string $source): ?string
    {
        try {
            $row = DB::table('content_translations')
                ->where('hash', $hash)
                ->where('locale', $locale)
                ->first(['translation']);

            if ($row !== null) {
                return $row->translation;
            }

            // Перевода ещё нет — ставим в очередь; фоновая задача
            // translations:fill переведёт его за минуту-другую
            DB::table('content_translations')->insertOrIgnore([
                'hash' => $hash,
                'locale' => $locale,
                'source' => $source,
                'attempts' => 0,
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        } catch (Throwable) {
            // Перевод — украшение: без таблицы (миграция ещё не прошла)
            // страница должна открыться с оригиналом, а не с ошибкой
        }

        return null;
    }
}
