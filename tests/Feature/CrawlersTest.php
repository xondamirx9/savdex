<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Http\Middleware\BlockGreedyCrawlers;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class CrawlersTest extends TestCase
{
    use RefreshDatabase;

    /** Робот из списка не должен дойти ни до маршрута, ни до базы. */
    #[Test]
    public function ссылочный_робот_получает_отказ(): void
    {
        $this->withServerVariables(['HTTP_USER_AGENT' => 'Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)'])
            ->get('/')
            ->assertStatus(403)
            ->assertHeader('Content-Type', 'text/plain; charset=utf-8');
    }

    /** Отказ обязан быть дешёвым: страница ошибки на Inertia — это ровно та работа, которой мы избегаем. */
    #[Test]
    public function отказ_не_рисует_страницу_ошибки(): void
    {
        $body = $this->withServerVariables(['HTTP_USER_AGENT' => 'AhrefsBot/7.0'])
            ->get('/')
            ->getContent();

        $this->assertStringNotContainsString('<html', (string) $body);
        $this->assertLessThan(200, strlen((string) $body));
    }

    /** Робот представляется длинной строкой, и регистр в ней у каждого свой. */
    #[Test]
    public function имя_робота_ищется_без_учёта_регистра(): void
    {
        foreach (['AHREFSBOT/7.0', 'ahrefsbot', 'Mozilla/5.0 (compatible; SemrushBot/7~bl)'] as $agent) {
            $this->withServerVariables(['HTTP_USER_AGENT' => $agent])
                ->get('/')
                ->assertStatus(403);
        }
    }

    /** Весь список обязан отказывать — иначе запись в нём ничего не значит. */
    #[Test]
    public function отказ_получает_каждый_из_списка(): void
    {
        foreach (BlockGreedyCrawlers::CRAWLERS as $crawler) {
            $this->withServerVariables(['HTTP_USER_AGENT' => "Mozilla/5.0 (compatible; {$crawler}/1.0)"])
                ->get('/')
                ->assertStatus(403, "{$crawler} должен получать отказ");
        }
    }

    /**
     * Главное в этой правке — кого мы НЕ трогаем. Поисковики приводят
     * покупателей; ошибка здесь тише, чем авария, и дороже.
     */
    #[Test]
    public function поисковики_проходят(): void
    {
        $engines = [
            'Googlebot' => 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            'YandexBot' => 'Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)',
            'bingbot' => 'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
            'DuckDuckBot' => 'DuckDuckBot/1.1; (+http://duckduckgo.com/duckduckgo-help-pages/results/duckduckbot/)',
            'Applebot' => 'Mozilla/5.0 (compatible; Applebot/0.1; +http://www.apple.com/go/applebot)',
            'PetalBot' => 'Mozilla/5.0 (compatible; PetalBot;+https://webmaster.petalsearch.com/site/petalbot)',
            'человек' => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36',
            'проверка Render' => 'Render/1.0',
        ];

        foreach ($engines as $name => $agent) {
            $this->withServerVariables(['HTTP_USER_AGENT' => $agent])
                ->get('/')
                ->assertStatus(200, "{$name} не должен получать отказ");
        }
    }

    /** Пустой User-Agent — не повод отказывать: так ходят проверки доступности. */
    #[Test]
    public function запрос_без_user_agent_проходит(): void
    {
        $this->get('/')->assertStatus(200);
    }

    /** robots.txt и middleware обязаны говорить одно и то же. */
    #[Test]
    public function robots_txt_перечисляет_тот_же_список(): void
    {
        $body = $this->get('/robots.txt')->assertOk()->getContent();

        foreach (BlockGreedyCrawlers::CRAWLERS as $crawler) {
            $this->assertStringContainsString("User-agent: {$crawler}", (string) $body);
        }

        foreach (['Googlebot', 'YandexBot', 'bingbot'] as $engine) {
            $this->assertStringNotContainsString("User-agent: {$engine}", (string) $body);
        }

        $this->assertStringContainsString('Sitemap:', (string) $body);
    }
}
