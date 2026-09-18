<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Регистрация бота у Telegram одной командой.
 *
 * Адрес приходилось собирать руками, подставляя в него токен
 * и секрет. Так в строку и уезжает «<ТОКЕН>» как есть: Telegram
 * отвечает «Not Found», а человек ищет ошибку в сайте, которого
 * она не касается.
 */
class TelegramWebhookCommandTest extends TestCase
{
    use RefreshDatabase;

    private function configure(): void
    {
        config([
            'services.telegram.bot_token' => '123:test-token',
            'services.telegram.bot_username' => 'savdex_bot',
            'services.telegram.webhook_secret' => 'secret-hook',
        ]);
    }

    #[Test]
    public function команда_сообщает_телеграму_адрес_из_настроек(): void
    {
        $this->configure();
        Http::fake(['api.telegram.org/*' => Http::response(['ok' => true, 'description' => 'Webhook was set'])]);

        $this->artisan('telegram:webhook')
            ->expectsOutputToContain('/telegram/webhook/secret-hook')
            ->assertSuccessful();

        Http::assertSent(fn ($request): bool => str_contains($request->url(), '/bot123:test-token/setWebhook')
            && str_ends_with((string) $request['url'], '/telegram/webhook/secret-hook'));
    }

    /** Чужой токен Telegram не узнаёт — говорим об этом прямо. */
    #[Test]
    public function неверный_токен_объясняется_по_русски(): void
    {
        $this->configure();
        Http::fake(['api.telegram.org/*' => Http::response(['ok' => false, 'description' => 'Not Found'], 404)]);

        $this->artisan('telegram:webhook')
            ->expectsOutputToContain('TELEGRAM_BOT_TOKEN')
            ->assertFailed();
    }

    #[Test]
    public function без_настроек_команда_говорит_чего_не_хватает(): void
    {
        config([
            'services.telegram.bot_token' => null,
            'services.telegram.bot_username' => null,
            'services.telegram.webhook_secret' => null,
        ]);

        $this->artisan('telegram:webhook')
            ->expectsOutputToContain('TELEGRAM_BOT_TOKEN')
            ->assertFailed();

        // Токен есть, секрета нет — адрес собрать не из чего
        config(['services.telegram.bot_token' => '123:t', 'services.telegram.bot_username' => 'savdex_bot']);

        $this->artisan('telegram:webhook')
            ->expectsOutputToContain('TELEGRAM_WEBHOOK_SECRET')
            ->assertFailed();
    }

    #[Test]
    public function показ_состояния_предупреждает_о_расхождении(): void
    {
        $this->configure();
        Http::fake(['api.telegram.org/*' => Http::response([
            'ok' => true,
            'result' => ['url' => 'https://savdex.uz/telegram/webhook/staryy', 'pending_update_count' => 3],
        ])]);

        $this->artisan('telegram:webhook --info')
            ->expectsOutputToContain('staryy')
            ->expectsOutputToContain('secret-hook')
            ->assertSuccessful();
    }

    #[Test]
    public function адрес_снимается(): void
    {
        $this->configure();
        Http::fake(['api.telegram.org/*' => Http::response(['ok' => true, 'description' => 'Webhook was deleted'])]);

        $this->artisan('telegram:webhook --delete')->assertSuccessful();

        Http::assertSent(fn ($request): bool => str_contains($request->url(), 'deleteWebhook'));
    }

    /** Бот, который молчит на «/start», читается как сломанный. */
    #[Test]
    public function бот_отвечает_на_голый_старт(): void
    {
        $this->configure();
        Http::fake(['api.telegram.org/*' => Http::response(['ok' => true])]);

        $this->postJson('/telegram/webhook/secret-hook', [
            'message' => ['chat' => ['id' => 778899], 'text' => '/start'],
        ])->assertNoContent();

        Http::assertSent(function ($request): bool {
            $this->assertSame('778899', (string) $request['chat_id']);
            $this->assertStringContainsString('SAVDEX', (string) $request['text']);
            $this->assertStringContainsString('Привязать Telegram', (string) $request['text']);

            return true;
        });
    }
}
