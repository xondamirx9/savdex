<?php

declare(strict_types=1);

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Throwable;

/**
 * Машинный перевод пользовательского контента.
 *
 * Продавцы пишут объявления по-русски, а каталог работает на пяти
 * языках — без перевода английская и узбекская версии показывали
 * русские заголовки. Используется публичный переводчик Google
 * (endpoint gtx — без ключа и оплаты): для площадки с десятками
 * объявлений его хватает; при росте объёмов сюда встаёт официальный
 * API — интерфейс сервиса не изменится.
 *
 * Любая ошибка возвращает null, а не исключение: перевод — украшение,
 * его отсутствие не должно ломать публикацию.
 */
class MachineTranslator
{
    /** Языки каталога, на которые переводится русский оригинал. */
    public const TARGETS = ['en', 'uz', 'tr', 'zh'];

    /** Коды Google, где они отличаются от кодов площадки. */
    private const GOOGLE_CODES = ['zh' => 'zh-CN'];

    /**
     * Предел одного запроса к переводчику, в символах.
     *
     * Больше — и Google отвечает ошибкой, а перевод молча не
     * складывается. Длинный текст (новость, описание компании)
     * режется по абзацам, куски переводятся по очереди.
     */
    private const CHUNK_LIMIT = 4000;

    /**
     * Последний запрос упёрся в ограничение переводчика (429).
     *
     * Бесплатный переводчик временно отказывает при частых запросах.
     * Такой отказ — не вина текста: фоновой задаче незачем списывать
     * на него попытку, достаточно подождать следующего прохода.
     */
    private bool $rateLimited = false;

    public function wasRateLimited(): bool
    {
        return $this->rateLimited;
    }

    public function translate(string $text, string $to): ?string
    {
        if (trim($text) === '' || ! config('services.machine_translation.enabled')) {
            return null;
        }

        $this->rateLimited = false;
        $parts = [];

        foreach (self::chunks($text) as $chunk) {
            $translated = $this->request($chunk, $to);

            // Недопереведённый текст хуже оригинала: половина абзацев
            // на одном языке, половина на другом
            if ($translated === null) {
                return null;
            }

            $parts[] = $translated;
        }

        return implode("\n\n", $parts);
    }

    /**
     * Куски не длиннее CHUNK_LIMIT: сначала по абзацам, слишком
     * длинный абзац — по предложениям, совсем без знаков препинания —
     * по символам.
     *
     * @return list<string>
     */
    public static function chunks(string $text): array
    {
        $text = trim($text);

        if (mb_strlen($text) <= self::CHUNK_LIMIT) {
            return [$text];
        }

        $pieces = [];

        foreach (preg_split('/\R{2,}/u', $text) ?: [] as $paragraph) {
            $paragraph = trim($paragraph);

            if ($paragraph === '') {
                continue;
            }

            if (mb_strlen($paragraph) <= self::CHUNK_LIMIT) {
                $pieces[] = $paragraph;

                continue;
            }

            foreach (preg_split('/(?<=[.!?…])\s+/u', $paragraph) ?: [] as $sentence) {
                foreach (mb_str_split($sentence, self::CHUNK_LIMIT) as $piece) {
                    $pieces[] = $piece;
                }
            }
        }

        // Мелкие куски склеиваются обратно: абзац за абзацем, пока
        // влезает, — меньше запросов и переводчик видит контекст
        $chunks = [];
        $current = '';

        foreach ($pieces as $piece) {
            $candidate = $current === '' ? $piece : $current."\n\n".$piece;

            if (mb_strlen($candidate) > self::CHUNK_LIMIT && $current !== '') {
                $chunks[] = $current;
                $current = $piece;
            } else {
                $current = $candidate;
            }
        }

        if ($current !== '') {
            $chunks[] = $current;
        }

        return $chunks;
    }

    /**
     * Один запрос к переводчику.
     *
     * Текст уходит телом POST, а не в адресе: адрес длиннее пары тысяч
     * символов Google отвергает с ошибкой 400, и текст новости целиком
     * так и не переводился — оставался русским на всех языках.
     */
    private function request(string $text, string $to): ?string
    {
        try {
            $response = Http::timeout(15)
                ->asForm()
                ->post('https://translate.googleapis.com/translate_a/single?'.http_build_query([
                    'client' => 'gtx',
                    'sl' => 'auto',
                    'tl' => self::GOOGLE_CODES[$to] ?? $to,
                    'dt' => 't',
                ]), ['q' => $text]);
        } catch (Throwable) {
            return null;
        }

        $this->rateLimited = $response->status() === 429;

        if (! $response->ok()) {
            return null;
        }

        // Ответ — вложенный массив: [[["перевод","оригинал",…],…],…]
        $chunks = $response->json()[0] ?? null;

        if (! is_array($chunks)) {
            return null;
        }

        $translated = implode('', array_map(
            fn ($chunk): string => is_array($chunk) ? (string) ($chunk[0] ?? '') : '',
            $chunks,
        ));

        return trim($translated) !== '' ? trim($translated) : null;
    }
}
