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

    public function translate(string $text, string $to): ?string
    {
        if (trim($text) === '' || ! config('services.machine_translation.enabled')) {
            return null;
        }

        try {
            $response = Http::timeout(10)->get('https://translate.googleapis.com/translate_a/single', [
                'client' => 'gtx',
                'sl' => 'auto',
                'tl' => self::GOOGLE_CODES[$to] ?? $to,
                'dt' => 't',
                'q' => $text,
            ]);
        } catch (Throwable) {
            return null;
        }

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
