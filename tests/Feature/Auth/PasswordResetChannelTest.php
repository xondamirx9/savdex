<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use App\Services\PasswordResetDelivery;
use Illuminate\Auth\Notifications\ResetPassword;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Notification;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Ссылка на смену пароля — не только на почту.
 *
 * Рабочий ящик теряется вместе с сотрудником, который его заводил,
 * и вместе с ним человек терял учётную запись. Теперь ссылку можно
 * получить в Telegram или WhatsApp.
 *
 * Отправляется именно ссылка: паролей площадка не хранит даже у себя,
 * а пароль, отправленный сообщением, остался бы в переписке навсегда.
 */
class PasswordResetChannelTest extends TestCase
{
    use RefreshDatabase;

    private function configureMessengers(): void
    {
        config([
            'services.telegram.bot_token' => '123:test-token',
            'services.telegram.bot_username' => 'savdex_bot',
            'services.telegram.webhook_secret' => 'secret-hook',
            'services.whatsapp.token' => 'wa-token',
            'services.whatsapp.phone_number_id' => '555000',
        ]);
    }

    #[Test]
    public function без_настроенных_мессенджеров_на_форме_одна_почта(): void
    {
        config(['services.telegram.bot_token' => null, 'services.whatsapp.token' => null]);

        $this->get('/forgot-password')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->where('channels', ['mail']));
    }

    #[Test]
    public function настроенные_способы_приходят_на_форму(): void
    {
        $this->configureMessengers();

        $this->get('/forgot-password')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('channels', ['mail', 'telegram', 'whatsapp']));
    }

    #[Test]
    public function почта_работает_как_прежде(): void
    {
        Notification::fake();

        $user = User::factory()->create(['email' => 'owner@stroybaza.uz']);

        $this->post('/forgot-password', ['email' => 'owner@stroybaza.uz'])
            ->assertSessionHas('status');

        Notification::assertSentTo($user, ResetPassword::class);
    }

    #[Test]
    public function ссылка_уходит_в_телеграм_привязанному_аккаунту(): void
    {
        $this->configureMessengers();
        Http::fake(['api.telegram.org/*' => Http::response(['ok' => true])]);

        User::factory()->create(['email' => 'owner@stroybaza.uz', 'telegram_chat_id' => '778899']);

        $this->post('/forgot-password', ['email' => 'owner@stroybaza.uz', 'channel' => 'telegram'])
            ->assertSessionHas('status');

        Http::assertSent(function ($request): bool {
            $this->assertStringContainsString('123:test-token', $request->url());
            $this->assertSame('778899', $request['chat_id']);
            $this->assertStringContainsString(url('/reset-password/'), $request['text']);

            return true;
        });
    }

    #[Test]
    public function ссылка_уходит_в_whatsapp_на_телефон_профиля(): void
    {
        $this->configureMessengers();
        Http::fake(['graph.facebook.com/*' => Http::response(['messages' => [['id' => '1']]])]);

        User::factory()->create(['email' => 'owner@stroybaza.uz', 'phone' => '+998 71 200-00-00']);

        $this->post('/forgot-password', ['email' => 'owner@stroybaza.uz', 'channel' => 'whatsapp'])
            ->assertSessionHas('status');

        Http::assertSent(function ($request): bool {
            $this->assertSame('998712000000', $request['to']);
            $this->assertSame('template', $request['type']);
            $this->assertStringContainsString(
                url('/reset-password/'),
                $request['template']['components'][0]['parameters'][0]['text'],
            );

            return true;
        });
    }

    /**
     * Ответ одинаков всегда: иначе форма показывает, зарегистрирован
     * ли адрес и привязан ли у человека Telegram.
     */
    #[Test]
    public function ответ_не_выдаёт_ни_аккаунт_ни_привязку(): void
    {
        $this->configureMessengers();
        Http::fake();

        User::factory()->create(['email' => 'owner@stroybaza.uz', 'telegram_chat_id' => null]);

        $withAccount = $this->post('/forgot-password', ['email' => 'owner@stroybaza.uz', 'channel' => 'telegram']);
        $withoutAccount = $this->post('/forgot-password', ['email' => 'nobody@example.com', 'channel' => 'telegram']);

        $this->assertSame(
            $withAccount->getSession()->get('status'),
            $withoutAccount->getSession()->get('status'),
        );

        // Непривязанному и несуществующему ничего не отправлено
        Http::assertNothingSent();
    }

    /** Способ, которого площадка не умеет, молча становится почтой. */
    #[Test]
    public function неизвестный_способ_подменяется_почтой(): void
    {
        Notification::fake();
        config(['services.telegram.bot_token' => null, 'services.whatsapp.token' => null]);

        $user = User::factory()->create(['email' => 'owner@stroybaza.uz', 'telegram_chat_id' => '778899']);

        $this->post('/forgot-password', ['email' => 'owner@stroybaza.uz', 'channel' => 'telegram'])
            ->assertSessionHas('status');

        Notification::assertSentTo($user, ResetPassword::class);
    }

    #[Test]
    public function ссылка_из_телеграма_меняет_пароль(): void
    {
        $this->configureMessengers();
        Http::fake(['api.telegram.org/*' => Http::response(['ok' => true])]);

        $user = User::factory()->create(['email' => 'owner@stroybaza.uz', 'telegram_chat_id' => '778899']);

        $this->post('/forgot-password', ['email' => 'owner@stroybaza.uz', 'channel' => 'telegram']);

        $link = '';
        Http::assertSent(function ($request) use (&$link): bool {
            preg_match('#'.preg_quote(url('/reset-password/'), '#').'\S+#', (string) $request['text'], $m);
            $link = $m[0] ?? '';

            return true;
        });

        $this->assertNotSame('', $link);

        parse_str((string) parse_url($link, PHP_URL_QUERY), $query);
        $token = basename((string) parse_url($link, PHP_URL_PATH));

        $this->post('/reset-password', [
            'token' => $token,
            'email' => $query['email'],
            'password' => 'Sovsem-Novyy-1',
            'password_confirmation' => 'Sovsem-Novyy-1',
        ])->assertRedirect('/login');

        $this->assertTrue(Hash::check('Sovsem-Novyy-1', $user->fresh()->password));
    }

    // ── Привязка Telegram ────────────────────────────────────

    #[Test]
    public function кабинет_уводит_к_боту_с_одноразовым_токеном(): void
    {
        $this->configureMessengers();

        $user = User::factory()->create();

        // Заголовок Inertia приходит на запрос из приложения; обычный
        // POST получает тот же адрес в Location — проверяем оба
        $response = $this->actingAs($user)
            ->withHeaders(['X-Inertia' => 'true'])
            ->post('/cabinet/settings/telegram');

        $response->assertStatus(409);
        $location = $response->headers->get('X-Inertia-Location');

        $this->assertStringStartsWith('https://t.me/savdex_bot?start=', (string) $location);

        $token = substr((string) $location, strlen('https://t.me/savdex_bot?start='));

        $this->assertSame($user->id, Cache::get('telegram.link.'.$token));
    }

    #[Test]
    public function бот_привязывает_чат_по_токену_и_второй_раз_не_срабатывает(): void
    {
        $this->configureMessengers();
        Http::fake(['api.telegram.org/*' => Http::response(['ok' => true])]);

        $user = User::factory()->create();
        Cache::put('telegram.link.abc123', $user->id, now()->addMinutes(15));

        $update = [
            'message' => [
                'chat' => ['id' => 778899],
                'from' => ['username' => 'stroybaza'],
                'text' => '/start abc123',
            ],
        ];

        $this->postJson('/telegram/webhook/secret-hook', $update)->assertNoContent();

        $user->refresh();

        $this->assertSame('778899', $user->telegram_chat_id);
        $this->assertSame('stroybaza', $user->telegram_username);
        $this->assertNotNull($user->telegram_linked_at);

        // Пересланная ссылка не привяжет чужой Telegram: токен одноразовый
        $other = User::factory()->create();
        $this->postJson('/telegram/webhook/secret-hook', [
            'message' => ['chat' => ['id' => 111], 'text' => '/start abc123'],
        ])->assertNoContent();

        $this->assertNull($other->fresh()->telegram_chat_id);
    }

    #[Test]
    public function чужой_адрес_вебхука_не_отвечает(): void
    {
        $this->configureMessengers();

        $this->postJson('/telegram/webhook/podobrannyy-sekret', [
            'message' => ['chat' => ['id' => 1], 'text' => '/start abc'],
        ])->assertNotFound();
    }

    #[Test]
    public function привязку_можно_снять(): void
    {
        $this->configureMessengers();

        $user = User::factory()->create(['telegram_chat_id' => '778899', 'telegram_username' => 'stroybaza']);

        $this->actingAs($user)->delete('/cabinet/settings/telegram')->assertRedirect();

        $user->refresh();

        $this->assertNull($user->telegram_chat_id);
        $this->assertNull($user->telegram_username);
    }

    #[Test]
    public function настройки_кабинета_показывают_состояние_привязки(): void
    {
        $this->configureMessengers();

        $user = User::factory()->create(['telegram_chat_id' => '778899', 'telegram_username' => 'stroybaza']);

        $this->actingAs($user)->get('/cabinet/settings')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('telegram.available', true)
                ->where('telegram.linked', true)
                ->where('telegram.username', 'stroybaza'));
    }

    #[Test]
    public function способы_отправки_считаются_по_настройкам(): void
    {
        config(['services.telegram.bot_token' => null, 'services.whatsapp.token' => null]);
        $this->assertSame(['mail'], app(PasswordResetDelivery::class)->channels());

        $this->configureMessengers();
        $this->assertSame(['mail', 'telegram', 'whatsapp'], app(PasswordResetDelivery::class)->channels());
    }
}
