<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Разметка текста страницы из админки — «О компании», «Инструкция»,
 * «Правила».
 *
 * Страница — не сплошные абзацы: в инструкции шаги с подсказками,
 * в правилах предупреждение и список. Вёрстку в админку не пускаем
 * (HTML из текстового поля — это и поломанная страница, и XSS), а
 * несколько понятных пометок в начале строки превращаем в блоки,
 * которые рисует сайт. Блоки разделяются пустой строкой:
 *
 *     ## Подзаголовок
 *
 *     1. Шаг — жирным
 *     Подсказка к шагу — строкой ниже
 *     2. Следующий шаг
 *
 *     - Пункт списка с галочкой
 *
 *     ! Предупреждение — жирным
 *     Пояснение к нему
 *
 *     Всё остальное — обычный абзац.
 *
 * Та же подсказка — у поля «Текст» в админке на Python
 * (python/savdex/site/pages_admin.py).
 */
final class PageBody
{
    /**
     * @return list<array{type: string, text?: string, title?: string, items?: list<mixed>}>
     */
    public static function blocks(?string $text): array
    {
        $blocks = [];

        foreach (preg_split('/\R\s*\R/u', trim((string) $text)) ?: [] as $chunk) {
            $lines = array_values(array_filter(
                array_map('trim', preg_split('/\R/u', trim($chunk)) ?: []),
                fn (string $line): bool => $line !== '',
            ));

            if ($lines === []) {
                continue;
            }

            $blocks[] = self::block($lines);
        }

        return $blocks;
    }

    /**
     * Все строки блоков — для перевода одним запросом.
     *
     * @param  list<array<string, mixed>>  $blocks
     * @return list<string>
     */
    public static function strings(array $blocks): array
    {
        $strings = [];

        array_walk_recursive($blocks, function (mixed $value, string|int $key) use (&$strings): void {
            if ($key !== 'type' && is_string($value) && $value !== '') {
                $strings[] = $value;
            }
        });

        return $strings;
    }

    /**
     * Те же блоки с каждой строкой, пропущенной через $translate.
     *
     * Переводится текст, а не разметка: пометки «##», «1.», «-»
     * переводчик мог бы потерять или перевести, и перевод рассыпался бы
     * в сплошные абзацы.
     *
     * @param  list<array<string, mixed>>  $blocks
     * @param  callable(string): string  $translate
     * @return list<array<string, mixed>>
     */
    public static function map(array $blocks, callable $translate): array
    {
        array_walk_recursive($blocks, function (mixed &$value, string|int $key) use ($translate): void {
            if ($key !== 'type' && is_string($value) && $value !== '') {
                $value = $translate($value);
            }
        });

        return $blocks;
    }

    /**
     * @param  non-empty-list<string>  $lines
     * @return array{type: string, text?: string, title?: string, items?: list<mixed>}
     */
    private static function block(array $lines): array
    {
        $first = $lines[0];

        if (str_starts_with($first, '## ')) {
            return ['type' => 'heading', 'text' => self::join([substr($first, 3), ...array_slice($lines, 1)])];
        }

        if (str_starts_with($first, '! ')) {
            return ['type' => 'note', 'title' => trim(substr($first, 2)), 'text' => self::join(array_slice($lines, 1))];
        }

        if (preg_match('/^\d{1,2}[.)]\s/u', $first) === 1) {
            return ['type' => 'steps', 'items' => self::steps($lines)];
        }

        if (str_starts_with($first, '- ')) {
            $items = [];

            foreach ($lines as $line) {
                // Строка без дефиса продолжает предыдущий пункт
                if (str_starts_with($line, '- ') || $items === []) {
                    $items[] = trim(preg_replace('/^-\s/u', '', $line) ?? $line);
                } else {
                    $items[array_key_last($items)] .= ' '.$line;
                }
            }

            return ['type' => 'list', 'items' => $items];
        }

        return ['type' => 'text', 'text' => self::join($lines)];
    }

    /**
     * @param  non-empty-list<string>  $lines
     * @return list<array{title: string, hint: string}>
     */
    private static function steps(array $lines): array
    {
        $steps = [];

        foreach ($lines as $line) {
            if (preg_match('/^\d{1,2}[.)]\s+(.*)$/u', $line, $m) === 1) {
                $steps[] = ['title' => trim($m[1]), 'hint' => ''];
            } else {
                $last = array_key_last($steps);
                $steps[$last]['hint'] = trim($steps[$last]['hint'].' '.$line);
            }
        }

        return $steps;
    }

    /** @param  list<string>  $lines */
    private static function join(array $lines): string
    {
        return trim(implode(' ', $lines));
    }
}
