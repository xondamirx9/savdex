<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use App\Models\NewsPost;
use App\Support\Locales;
use Illuminate\Http\Response;

/**
 * Карта сайта.
 *
 * Собирается на лету, а не файлом на диске: объявления появляются
 * и истекают ежедневно, и файл, обновляемый заданием раз в сутки,
 * половину времени врал бы — присылал робота на снятые объявления
 * и умалчивал о свежих.
 *
 * Разбита на разделы: одним файлом больше 50 000 адресов отдавать
 * нельзя по спецификации, а объявлений на живой площадке будет
 * больше. Индекс ссылается на части, каждая часть — свой раздел.
 */
class SitemapController extends Controller
{
    /**
     * Объявлений на файл.
     *
     * Предел спецификации — 50 000 адресов. Каждое объявление даёт
     * пять адресов, по одному на язык, поэтому берём пять тысяч:
     * 25 000 записей с перечнем языковых версий у каждой — это ещё
     * и разумный размер файла.
     */
    private const CHUNK = 5000;

    /** Индекс: перечень частей. */
    public function index(): Response
    {
        $parts = ['static', 'categories', 'companies'];

        $listingPages = (int) ceil(Listing::where('status', Listing::STATUS_ACTIVE)->count() / self::CHUNK);

        foreach (range(1, max(1, $listingPages)) as $page) {
            $parts[] = "listings-{$page}";
        }

        if (NewsPost::query()->where('status', 'published')->exists()) {
            $parts[] = 'news';
        }

        $xml = view('sitemap.index', [
            'parts' => array_map(fn (string $p): string => url("/sitemap-{$p}.xml"), $parts),
            'lastmod' => now()->toAtomString(),
        ])->render();

        return $this->xml($xml);
    }

    public function part(string $name): Response
    {
        $urls = match (true) {
            $name === 'static' => $this->static(),
            $name === 'categories' => $this->categories(),
            $name === 'companies' => $this->companies(),
            $name === 'news' => $this->news(),
            (bool) preg_match('/^listings-(\d+)$/', $name, $m) => $this->listings((int) $m[1]),
            default => null,
        };

        abort_if($urls === null, 404);

        return $this->xml(view('sitemap.urlset', ['urls' => $this->withLocales($urls)])->render());
    }

    /**
     * Развернуть каждый адрес во все языковые версии.
     *
     * Раздел на пяти языках — это пять адресов, а не один: без них
     * робот узнаёт о переводах только случайно, по ссылкам, и
     * индексирует их с большой задержкой. Заодно у каждого адреса
     * перечисляются остальные версии — так поисковик понимает, что
     * это переводы одной страницы, а не пять похожих страниц.
     *
     * @param  list<array<string, string>>  $urls
     * @return list<array<string, mixed>>
     */
    private function withLocales(array $urls): array
    {
        $out = [];

        foreach ($urls as $url) {
            $path = $url['loc'];
            $root = url('/');
            $path = str_starts_with($path, $root) ? substr($path, strlen($root)) : $path;
            $path = $path === '' ? '/' : $path;

            $alternates = [];
            foreach (Locales::ALL as $code => $meta) {
                $alternates[$meta['hreflang']] = Locales::url($path, $code);
            }
            $alternates['x-default'] = Locales::url($path, Locales::DEFAULT);

            foreach (Locales::codes() as $code) {
                $out[] = [...$url, 'loc' => Locales::url($path, $code), 'alternates' => $alternates];
            }
        }

        return $out;
    }

    /**
     * Постоянные страницы.
     *
     * Кабинет, админка и служебные адреса сюда не попадают: карта сайта
     * — приглашение роботу, а приглашать его в личный кабинет незачем.
     *
     * @return list<array{loc: string, priority: string, changefreq: string}>
     */
    private function static(): array
    {
        return [
            ['loc' => url('/'), 'priority' => '1.0', 'changefreq' => 'daily'],
            ['loc' => url('/catalog'), 'priority' => '0.9', 'changefreq' => 'hourly'],
            ['loc' => url('/companies'), 'priority' => '0.9', 'changefreq' => 'daily'],
            ['loc' => url('/pricing'), 'priority' => '0.7', 'changefreq' => 'monthly'],
            ['loc' => url('/about'), 'priority' => '0.5', 'changefreq' => 'monthly'],
            ['loc' => url('/news'), 'priority' => '0.6', 'changefreq' => 'weekly'],
            // Разделы из подвала: индексируемые страницы, которых
            // роботу иначе не найти иначе как по ссылкам с витрины
            ['loc' => url('/countries'), 'priority' => '0.5', 'changefreq' => 'monthly'],
            ['loc' => url('/partners'), 'priority' => '0.4', 'changefreq' => 'monthly'],
            ['loc' => url('/contact'), 'priority' => '0.4', 'changefreq' => 'yearly'],
            // Оферту и политику ищут по названию площадки перед оплатой;
            // приоритет низкий, но в индексе они быть должны
            ['loc' => url('/terms'), 'priority' => '0.3', 'changefreq' => 'yearly'],
            ['loc' => url('/payment'), 'priority' => '0.3', 'changefreq' => 'yearly'],
            ['loc' => url('/security'), 'priority' => '0.3', 'changefreq' => 'yearly'],
            ['loc' => url('/privacy'), 'priority' => '0.3', 'changefreq' => 'yearly'],
            ['loc' => url('/refunds'), 'priority' => '0.3', 'changefreq' => 'yearly'],
        ];
    }

    /**
     * Категории каталога.
     *
     * Единственные фильтрованные адреса, которые роботу нужны: под них
     * есть спрос в поиске («стройматериалы оптом»), и содержимое у них
     * заметно разное. Остальные сочетания фильтров закрыты noindex.
     *
     * @return list<array{loc: string, priority: string, changefreq: string}>
     */
    private function categories(): array
    {
        return Category::query()
            ->where('is_active', true)
            ->withCount(['listings as active' => fn ($q) => $q->where('status', Listing::STATUS_ACTIVE)])
            ->get()
            // Пустая категория роботу не нужна: он придёт на страницу
            // без товаров и в следующий раз зайдёт нескоро
            ->filter(fn (Category $c): bool => $c->active > 0)
            ->map(fn (Category $c): array => [
                'loc' => url('/catalog?category='.$c->id),
                'priority' => '0.8',
                'changefreq' => 'daily',
            ])
            ->values()
            ->all();
    }

    /** @return list<array<string, string>> */
    private function companies(): array
    {
        return Company::query()
            ->where('status', Company::STATUS_ACTIVE)
            ->whereNotNull('slug')
            ->get(['slug', 'updated_at'])
            ->map(fn (Company $c): array => [
                'loc' => url('/company/'.$c->slug),
                'lastmod' => $c->updated_at?->toAtomString(),
                'priority' => '0.7',
                'changefreq' => 'weekly',
            ])
            ->all();
    }

    /** @return list<array<string, string>> */
    private function listings(int $page): array
    {
        return Listing::query()
            ->where('status', Listing::STATUS_ACTIVE)
            ->whereNotNull('slug')
            ->orderBy('id')
            ->forPage($page, self::CHUNK)
            ->get(['slug', 'updated_at'])
            ->map(fn (Listing $l): array => [
                'loc' => url('/listing/'.$l->slug),
                'lastmod' => $l->updated_at?->toAtomString(),
                'priority' => '0.6',
                'changefreq' => 'weekly',
            ])
            ->all();
    }

    /** @return list<array<string, string>> */
    private function news(): array
    {
        return NewsPost::query()
            ->where('status', 'published')
            ->get(['slug', 'updated_at'])
            ->map(fn (NewsPost $n): array => [
                'loc' => url('/news/'.$n->slug),
                'lastmod' => $n->updated_at?->toAtomString(),
                'priority' => '0.5',
                'changefreq' => 'monthly',
            ])
            ->all();
    }

    private function xml(string $body): Response
    {
        return response($body, 200, [
            'Content-Type' => 'application/xml; charset=utf-8',
            // Час: чаще робот и не заходит, а собирать карту на каждый
            // его запрос — лишняя работа для базы
            'Cache-Control' => 'public, max-age=3600',
        ]);
    }
}
