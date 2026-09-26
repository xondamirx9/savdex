<?php

declare(strict_types=1);

namespace App\Support\Microsite;

/**
 * Оформление мини-сайта: шаблон и дизайн-токены.
 *
 * Компания не пишет CSS — она выбирает значения из заданного набора:
 * два цвета, светлую или тёмную тему, шрифты и скругления. Из них
 * здесь собираются CSS-переменные, которыми покрашены все шаблоны.
 *
 * Почему токены, а не свободный CSS: любые сочетания токенов дают
 * читаемую страницу, а свободный CSS — нет. Всё, что может сломать
 * читаемость, решается здесь, а не на совести компании: цвет текста
 * на кнопке подбирается под её фон, а слишком светлый фирменный цвет
 * для ссылок затемняется до контраста WCAG AA.
 *
 * Всё, что приходит снаружи, проходит normalize(): неизвестный шрифт,
 * кривой цвет или чужое поле заменяются значением по умолчанию.
 * В CSS-переменные попадают только проверенные значения — никакая
 * строка от компании в <style> дословно не уходит.
 */
final class SiteTheme
{
    public const TEMPLATES = ['classic', 'bold', 'minimal'];

    public const MODES = ['light', 'dark'];

    /** Скругления углов карточек и кнопок. */
    public const RADII = [
        'sharp' => '2px',
        'soft' => '10px',
        'round' => '22px',
    ];

    /**
     * Шрифты — только с кириллицей и узбекской латиницей: половина
     * посетителей читает по-русски, и шрифт без кириллицы молча
     * подменялся бы системным посреди заголовка.
     *
     * Ключ — имя семейства на fonts.bunny.net, туда же ходит витрина.
     *
     * @var array<string, array{name: string, fallback: string}>
     */
    public const FONTS = [
        'manrope' => ['name' => 'Manrope', 'fallback' => 'sans-serif'],
        'inter' => ['name' => 'Inter', 'fallback' => 'sans-serif'],
        'montserrat' => ['name' => 'Montserrat', 'fallback' => 'sans-serif'],
        'rubik' => ['name' => 'Rubik', 'fallback' => 'sans-serif'],
        'nunito' => ['name' => 'Nunito', 'fallback' => 'sans-serif'],
        'pt-sans' => ['name' => 'PT Sans', 'fallback' => 'sans-serif'],
        'ibm-plex-sans' => ['name' => 'IBM Plex Sans', 'fallback' => 'sans-serif'],
        'oswald' => ['name' => 'Oswald', 'fallback' => 'sans-serif'],
        'playfair-display' => ['name' => 'Playfair Display', 'fallback' => 'serif'],
        'lora' => ['name' => 'Lora', 'fallback' => 'serif'],
        'pt-serif' => ['name' => 'PT Serif', 'fallback' => 'serif'],
    ];

    public const DEFAULTS = [
        'template' => 'classic',
        'primary' => '#1a56db',
        'accent' => '#f59e0b',
        'mode' => 'light',
        'heading_font' => 'manrope',
        'body_font' => 'manrope',
        'radius' => 'soft',
    ];

    /**
     * Готовые сочетания — отправная точка. Большинство компаний не
     * дизайнеры, и пустая палитра пугает сильнее, чем выбор из пяти.
     * Шаблон пресет не трогает: это отдельное решение.
     *
     * @var array<string, array<string, string>>
     */
    public const PRESETS = [
        'savdex' => ['primary' => '#1a56db', 'accent' => '#f59e0b', 'mode' => 'light', 'heading_font' => 'manrope', 'body_font' => 'manrope', 'radius' => 'soft'],
        'forest' => ['primary' => '#0f6e56', 'accent' => '#d4a017', 'mode' => 'light', 'heading_font' => 'lora', 'body_font' => 'pt-sans', 'radius' => 'soft'],
        'graphite' => ['primary' => '#f97316', 'accent' => '#38bdf8', 'mode' => 'dark', 'heading_font' => 'oswald', 'body_font' => 'inter', 'radius' => 'sharp'],
        'terracotta' => ['primary' => '#b4532a', 'accent' => '#2f6f73', 'mode' => 'light', 'heading_font' => 'playfair-display', 'body_font' => 'nunito', 'radius' => 'round'],
        'royal' => ['primary' => '#5b3cc4', 'accent' => '#e11d74', 'mode' => 'light', 'heading_font' => 'montserrat', 'body_font' => 'rubik', 'radius' => 'round'],
    ];

    /** Фон и текст темы. Их компания не выбирает — только светлую или тёмную. */
    private const SURFACES = [
        'light' => ['bg' => '#ffffff', 'surface' => '#f6f7f9', 'text' => '#0f172a', 'muted' => '#5b6475', 'line' => '#e2e8f0'],
        'dark' => ['bg' => '#0b1120', 'surface' => '#141c2f', 'text' => '#e8ecf3', 'muted' => '#9aa4b8', 'line' => '#26314a'],
    ];

    /** Порог WCAG AA для обычного текста. */
    private const MIN_CONTRAST = 4.5;

    /**
     * Проверенное оформление: неизвестные поля отброшены, недопустимые
     * значения заменены значениями по умолчанию.
     *
     * @param  array<mixed>|null  $input
     * @return array<string, string>
     */
    public static function normalize(?array $input): array
    {
        $input ??= [];
        $theme = self::DEFAULTS;

        if (in_array($input['template'] ?? null, self::TEMPLATES, true)) {
            $theme['template'] = $input['template'];
        }

        foreach (['primary', 'accent'] as $key) {
            if (is_string($input[$key] ?? null) && self::isHex($input[$key])) {
                $theme[$key] = strtolower($input[$key]);
            }
        }

        if (in_array($input['mode'] ?? null, self::MODES, true)) {
            $theme['mode'] = $input['mode'];
        }

        foreach (['heading_font', 'body_font'] as $key) {
            if (is_string($input[$key] ?? null) && isset(self::FONTS[$input[$key]])) {
                $theme[$key] = $input[$key];
            }
        }

        if (is_string($input['radius'] ?? null) && isset(self::RADII[$input['radius']])) {
            $theme['radius'] = $input['radius'];
        }

        return $theme;
    }

    /**
     * Правила проверки формы в кабинете. Проверка строже normalize():
     * там молча подставляется значение по умолчанию, а здесь человеку
     * нужно сказать, что введённое не подошло.
     *
     * @return array<string, list<string>>
     */
    public static function rules(): array
    {
        return [
            'theme' => ['required', 'array'],
            'theme.template' => ['required', 'in:'.implode(',', self::TEMPLATES)],
            'theme.primary' => ['required', 'regex:/^#[0-9a-fA-F]{6}$/'],
            'theme.accent' => ['required', 'regex:/^#[0-9a-fA-F]{6}$/'],
            'theme.mode' => ['required', 'in:'.implode(',', self::MODES)],
            'theme.heading_font' => ['required', 'in:'.implode(',', array_keys(self::FONTS))],
            'theme.body_font' => ['required', 'in:'.implode(',', array_keys(self::FONTS))],
            'theme.radius' => ['required', 'in:'.implode(',', array_keys(self::RADII))],
        ];
    }

    /**
     * CSS-переменные оформления. Имена начинаются с --ms-, чтобы
     * не пересечься с токенами витрины.
     *
     * @param  array<string, string>  $theme  результат normalize()
     * @return array<string, string>
     */
    public static function variables(array $theme): array
    {
        $s = self::SURFACES[$theme['mode']];
        $heading = self::FONTS[$theme['heading_font']];
        $body = self::FONTS[$theme['body_font']];

        return [
            '--ms-bg' => $s['bg'],
            '--ms-surface' => $s['surface'],
            '--ms-text' => $s['text'],
            '--ms-muted' => $s['muted'],
            '--ms-line' => $s['line'],
            '--ms-primary' => $theme['primary'],
            '--ms-on-primary' => self::readableOn($theme['primary']),
            // Для ссылок и заголовков на фоне страницы: жёлтый бренд
            // на белом фоне не читается, поэтому затемняется
            '--ms-primary-text' => self::legibleOn($theme['primary'], $s['bg'], $s['text']),
            '--ms-primary-soft' => self::mix($theme['primary'], $s['bg'], 0.88),
            '--ms-accent' => $theme['accent'],
            '--ms-on-accent' => self::readableOn($theme['accent']),
            '--ms-radius' => self::RADII[$theme['radius']],
            '--ms-font-heading' => "'{$heading['name']}', {$heading['fallback']}",
            '--ms-font-body' => "'{$body['name']}', {$body['fallback']}",
        ];
    }

    /** Переменные одной строкой — для <style> в шаблоне страницы. */
    public static function css(array $theme): string
    {
        $pairs = [];

        foreach (self::variables($theme) as $name => $value) {
            $pairs[] = "{$name}:{$value}";
        }

        return implode(';', $pairs);
    }

    /** Адрес стилей шрифтов: оба семейства одним запросом. */
    public static function fontsUrl(array $theme): string
    {
        $families = array_unique([$theme['heading_font'], $theme['body_font']]);

        return 'https://fonts.bunny.net/css?family='
            .implode('|', array_map(fn (string $f): string => $f.':400,600,700', $families))
            .'&display=swap';
    }

    /**
     * Варианты для формы в кабинете.
     *
     * @return array<string, mixed>
     */
    public static function options(): array
    {
        return [
            'templates' => self::TEMPLATES,
            'modes' => self::MODES,
            'radii' => array_keys(self::RADII),
            'fonts' => array_map(
                fn (string $key): array => ['key' => $key, 'name' => self::FONTS[$key]['name']],
                array_keys(self::FONTS),
            ),
            'presets' => self::PRESETS,
            'fonts_url' => 'https://fonts.bunny.net/css?family='
                .implode('|', array_map(fn (string $f): string => $f.':600', array_keys(self::FONTS)))
                .'&display=swap',
        ];
    }

    // ── Цвет ─────────────────────────────────────────────────

    private static function isHex(string $value): bool
    {
        return preg_match('/^#[0-9a-fA-F]{6}$/', $value) === 1;
    }

    /** Белый или тёмный текст — что читается лучше на этом фоне. */
    public static function readableOn(string $background): string
    {
        $white = self::contrast('#ffffff', $background);
        $ink = self::contrast('#0f172a', $background);

        return $white >= $ink ? '#ffffff' : '#0f172a';
    }

    /**
     * Цвет, сдвинутый к цвету текста до читаемого контраста с фоном.
     * Шаг в десятую долю: оттенок бренда сохраняется настолько,
     * насколько позволяет читаемость.
     */
    public static function legibleOn(string $color, string $background, string $toward): string
    {
        for ($i = 0; $i <= 10; $i++) {
            $candidate = self::mix($color, $toward, $i / 10);

            if (self::contrast($candidate, $background) >= self::MIN_CONTRAST) {
                return $candidate;
            }
        }

        return $toward;
    }

    /** Контрастность по WCAG 2.x: от 1 до 21. */
    public static function contrast(string $a, string $b): float
    {
        $la = self::luminance($a);
        $lb = self::luminance($b);

        return (max($la, $lb) + 0.05) / (min($la, $lb) + 0.05);
    }

    /** Смесь двух цветов: $amount = 0 — первый, 1 — второй. */
    public static function mix(string $from, string $to, float $amount): string
    {
        $a = self::rgb($from);
        $b = self::rgb($to);

        $mixed = array_map(
            fn (int $x, int $y): int => (int) round($x + ($y - $x) * $amount),
            $a,
            $b,
        );

        return sprintf('#%02x%02x%02x', ...$mixed);
    }

    private static function luminance(string $hex): float
    {
        $channels = array_map(function (int $c): float {
            $c /= 255;

            return $c <= 0.03928 ? $c / 12.92 : (($c + 0.055) / 1.055) ** 2.4;
        }, self::rgb($hex));

        return 0.2126 * $channels[0] + 0.7152 * $channels[1] + 0.0722 * $channels[2];
    }

    /** @return array{int, int, int} */
    private static function rgb(string $hex): array
    {
        $hex = ltrim($hex, '#');

        return [
            (int) hexdec(substr($hex, 0, 2)),
            (int) hexdec(substr($hex, 2, 2)),
            (int) hexdec(substr($hex, 4, 2)),
        ];
    }
}
