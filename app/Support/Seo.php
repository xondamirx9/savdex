<?php

declare(strict_types=1);

namespace App\Support;

use Illuminate\Support\Str;

/**
 * Мета-теги страницы, отдаваемые сервером.
 *
 * Inertia проставляет заголовок и описание скриптом, уже в браузере.
 * Живому человеку этого достаточно, а роботу — нет:
 *
 * — превью-боты Telegram, WhatsApp и Facebook не выполняют JavaScript
 *   вообще. Ссылка на объявление, отправленная в Telegram — главный
 *   канал распространения на этом рынке, — выглядела голым адресом;
 * — Яндекс отрисовывает JavaScript неохотно и с задержкой, а в
 *   Узбекистане это второй поисковик после Google;
 * — Google JavaScript выполняет, но индексирует такую страницу
 *   позже и менее надёжно.
 *
 * Поэтому теги собираются в контроллере и печатаются в HTML сервером,
 * до того как страница попадёт браузеру. Клиентский <Head> при этом
 * остаётся: он обновляет заголовок вкладки при переходах без
 * перезагрузки, а серверные теги нужны для первого ответа.
 */
class Seo
{
    private string $title = 'SAVDEX';

    private string $description = '';

    private ?string $canonical = null;

    private ?string $image = null;

    private string $type = 'website';

    private bool $noindex = false;

    /** @var list<array<string, mixed>> */
    private array $schemas = [];

    public function title(string $title): self
    {
        $title = trim($title);

        // Заголовок часто собирается из поискового запроса, а его
        // набирают строчными: «цемент в Ташкенте» в выдаче выглядит
        // опечаткой. Регистр остальных букв не трогаем — в названиях
        // компаний он осмысленный
        $title = mb_strtoupper(mb_substr($title, 0, 1)).mb_substr($title, 1);

        // Длинный заголовок поисковик обрезает посреди слова, и в выдаче
        // остаётся огрызок. 60 знаков — то, что показывают целиком
        $this->title = Str::limit($title, 60, '');

        return $this;
    }

    public function description(?string $text): self
    {
        if ($text === null) {
            return $this;
        }

        // Описание из текста объявления: переносы и лишние пробелы
        // в сниппете выглядят рвано
        $clean = trim((string) preg_replace('/\s+/u', ' ', strip_tags($text)));

        $this->description = Str::limit($clean, 155, '…');

        return $this;
    }

    public function canonical(string $url): self
    {
        $this->canonical = $url;

        return $this;
    }

    public function image(?string $url): self
    {
        $this->image = $url;

        return $this;
    }

    public function type(string $type): self
    {
        $this->type = $type;

        return $this;
    }

    /**
     * Закрыть страницу от индексации.
     *
     * Нужно там, где страница осмысленна для человека и бесполезна
     * для поиска: результаты фильтров, вторые и последующие страницы
     * выдачи, личный кабинет. Каждая такая в индексе конкурирует
     * с основной за одни и те же запросы.
     */
    public function noindex(bool $value = true): self
    {
        $this->noindex = $value;

        return $this;
    }

    /** @param array<string, mixed> $schema */
    public function schema(array $schema): self
    {
        $this->schemas[] = $schema;

        return $this;
    }

    // ── Чтение из шаблона ────────────────────────────────────

    public function getTitle(): string
    {
        return $this->title === 'SAVDEX' ? $this->title : $this->title.' · SAVDEX';
    }

    public function getDescription(): string
    {
        return $this->description;
    }

    /**
     * Канонический адрес — всегда на текущем языке.
     *
     * Контроллеры задают путь без языка: canonical(url('/catalog')).
     * Язык подставляется здесь, иначе узбекская страница объявляла бы
     * канонической русскую, и весь узбекский раздел выпал бы из
     * индекса как «дубль».
     */
    public function getCanonical(): string
    {
        return Locales::url($this->path(), app()->getLocale());
    }

    /**
     * Адреса этой страницы на всех языках — для hreflang.
     *
     * x-default отдельной строкой: он говорит поисковику, что
     * показывать тому, чей язык в списке не нашёлся. Без него
     * Google выбирает сам, и обычно не тот, что нужен.
     *
     * @return array<string, string> hreflang => адрес
     */
    public function getAlternates(): array
    {
        $path = $this->path();

        $links = [];

        foreach (Locales::ALL as $code => $meta) {
            $links[$meta['hreflang']] = Locales::url($path, $code);
        }

        $links['x-default'] = Locales::url($path, Locales::DEFAULT);

        return $links;
    }

    /** Путь без языка и без домена — основа для сборки адресов. */
    private function path(): string
    {
        $url = $this->canonical ?? url()->current();
        $root = url('/');

        $path = str_starts_with($url, $root) ? substr($url, strlen($root)) : $url;

        return $path === '' ? '/' : $path;
    }

    /**
     * Картинка превью — своя либо фирменная заглушка.
     *
     * Пустого og:image быть не должно: у объявления может не быть
     * фотографий, и ссылка в Telegram превращалась в узкую строчку
     * без картинки — на фоне соседних сообщений её просто не видно.
     * Заглушка с логотипом даёт крупную карточку в любом случае.
     */
    public function getImage(): string
    {
        return $this->image ?? url('/og-cover.png');
    }

    public function getType(): string
    {
        return $this->type;
    }

    public function isNoindex(): bool
    {
        return $this->noindex;
    }

    /**
     * Разметка Schema.org одним блоком.
     *
     * Организация площадки добавляется всегда: она связывает все
     * страницы в один сайт и даёт поисковику знать, кто их публикует.
     */
    public function getJsonLd(): ?string
    {
        $schemas = [$this->organization(), ...$this->schemas];

        /*
         * Блок печатается сырым внутри <script type="application/ld+json">.
         * Название и описание компании задаёт сам пользователь, поэтому
         * шифруем угловые скобки и амперсанд: без JSON_HEX_TAG строка
         * «</script><script>…» в названии компании закрывала бы тег и
         * исполняла чужой скрипт на каждой странице визитки (XSS).
         * JSON_UNESCAPED_SLASHES убран намеренно — экранированный слэш
         * тоже мешает собрать «</script>».
         */
        return json_encode(
            count($schemas) === 1 ? $schemas[0] : ['@context' => 'https://schema.org', '@graph' => $schemas],
            JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_QUOT | JSON_HEX_APOS,
        ) ?: null;
    }

    /** @return array<string, mixed> */
    private function organization(): array
    {
        return [
            '@context' => 'https://schema.org',
            '@type' => 'Organization',
            'name' => 'SAVDEX',
            'url' => url('/'),
            'description' => 'B2B-площадка Узбекистана и Центральной Азии: поставщики и закупщики находят друг друга',
            'areaServed' => ['UZ', 'KZ', 'KG', 'TJ'],
        ];
    }
}
