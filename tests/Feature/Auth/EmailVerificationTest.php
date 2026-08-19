<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use App\Notifications\VerifyEmailCode;
use App\Support\EmailVerificationCode;
use Illuminate\Auth\Events\Verified;
use Illuminate\Auth\Notifications\ResetPassword;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Notification;
use Illuminate\Support\Facades\URL;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Подтверждение почты и восстановление пароля.
 *
 * Появился после боевого дефекта: регистрация падала с 500
 * «Route [verification.verify] not defined». Письмо строит ссылку
 * через route(), и отсутствие маршрута ломало регистрацию целиком —
 * причём уже ПОСЛЕ создания пользователя.
 */
class EmailVerificationTest extends TestCase
{
    use RefreshDatabase;

    private function payload(array $overrides = []): array
    {
        return array_merge([
            'name' => 'Рустам Каримов',
            'email' => 'rustam@company.uz',
            'phone' => '+998 90 123-45-67',
            'password' => 'Cement2026!x',
            'password_confirmation' => 'Cement2026!x',
            'terms' => true,
        ], $overrides);
    }

    /**
     * Главный тест: регистрация проходит целиком, без исключений.
     * Именно этот сценарий и падал в бою.
     */
    #[Test]
    public function регистрация_доходит_до_конца_и_шлёт_письмо(): void
    {
        Notification::fake();

        // После регистрации идёт шаг данных компании, письмо уходит сразу
        $this->post('/register', $this->payload())
            ->assertRedirect('/onboarding/company')
            ->assertSessionHasNoErrors();

        $user = User::where('email', 'rustam@company.uz')->firstOrFail();

        Notification::assertSentTo($user, VerifyEmailCode::class);
    }

    // ── Подтверждение кодом из письма ────────────────────────

    #[Test]
    public function код_из_письма_подтверждает_почту(): void
    {
        Event::fake([Verified::class]);

        $user = User::factory()->unverified()->create();
        $code = EmailVerificationCode::issue($user);

        $this->actingAs($user)
            ->post('/verify-email/code', ['code' => $code])
            ->assertRedirect('/cabinet')
            ->assertSessionHasNoErrors();

        $this->assertTrue($user->fresh()->hasVerifiedEmail());
        Event::assertDispatched(Verified::class);
    }

    #[Test]
    public function неверный_код_отклоняется(): void
    {
        $user = User::factory()->unverified()->create();
        EmailVerificationCode::issue($user);

        $this->actingAs($user)
            ->post('/verify-email/code', ['code' => '000000'])
            ->assertInvalid(['code']);

        $this->assertFalse($user->fresh()->hasVerifiedEmail());
    }

    /** Верный код одноразов: повторный ввод уже не срабатывает. */
    #[Test]
    public function код_работает_один_раз(): void
    {
        $user = User::factory()->unverified()->create();
        $code = EmailVerificationCode::issue($user);

        $this->assertTrue(EmailVerificationCode::check($user, $code));
        $this->assertFalse(EmailVerificationCode::check($user, $code));
    }

    /** После пяти неверных попыток гаснет даже правильный код. */
    #[Test]
    public function перебор_кода_гасит_его_после_лимита_попыток(): void
    {
        $user = User::factory()->unverified()->create();
        $code = EmailVerificationCode::issue($user);

        foreach (range(1, 5) as $i) {
            $this->assertFalse(EmailVerificationCode::check($user, '000000'));
        }

        $this->assertFalse(EmailVerificationCode::check($user, $code));
    }

    /** Повторное письмо выпускает новый код — старый перестаёт работать. */
    #[Test]
    public function новый_код_отменяет_старый(): void
    {
        $user = User::factory()->unverified()->create();

        $old = EmailVerificationCode::issue($user);
        $new = EmailVerificationCode::issue($user);

        $this->assertFalse(EmailVerificationCode::check($user, $old));
        $this->assertTrue(EmailVerificationCode::check($user, $new));
    }

    /** Код уходит в письме — и именно тот, который принимает проверка. */
    #[Test]
    public function письмо_содержит_рабочий_код(): void
    {
        Notification::fake();

        $user = User::factory()->unverified()->create();
        $user->sendEmailVerificationNotification();

        Notification::assertSentTo($user, VerifyEmailCode::class, function (VerifyEmailCode $n) use ($user): bool {
            return EmailVerificationCode::check($user, $n->code);
        });
    }

    #[Test]
    public function ссылка_из_письма_подтверждает_почту(): void
    {
        Event::fake([Verified::class]);

        $user = User::factory()->unverified()->create();

        $link = URL::temporarySignedRoute('verification.verify', now()->addHour(), [
            'id' => $user->id,
            'hash' => sha1($user->email),
        ]);

        $this->actingAs($user)->get($link)->assertRedirect('/cabinet');

        $this->assertTrue($user->fresh()->hasVerifiedEmail());
        Event::assertDispatched(Verified::class);
    }

    /** Подделанная или изменённая ссылка не должна срабатывать. */
    #[Test]
    public function неподписанная_ссылка_отклоняется(): void
    {
        $user = User::factory()->unverified()->create();

        $this->actingAs($user)
            ->get("/verify-email/{$user->id}/".sha1($user->email))
            ->assertForbidden();

        $this->assertFalse($user->fresh()->hasVerifiedEmail());
    }

    #[Test]
    public function чужая_ссылка_не_подтверждает_почту(): void
    {
        $user = User::factory()->unverified()->create();
        $other = User::factory()->unverified()->create();

        $link = URL::temporarySignedRoute('verification.verify', now()->addHour(), [
            'id' => $other->id,
            'hash' => sha1($other->email),
        ]);

        $this->actingAs($user)->get($link)->assertForbidden();

        $this->assertFalse($other->fresh()->hasVerifiedEmail());
    }

    #[Test]
    public function повторная_отправка_письма_работает(): void
    {
        Notification::fake();

        $user = User::factory()->unverified()->create();

        $this->actingAs($user)->post('/email/verification-notification')->assertRedirect();

        Notification::assertSentTo($user, VerifyEmailCode::class);
    }

    #[Test]
    public function подтверждённого_пользователя_не_держат_на_странице_ожидания(): void
    {
        $user = User::factory()->create(['email_verified_at' => now()]);

        $this->actingAs($user)->get('/verify-email')->assertRedirect('/cabinet');
    }

    // ── Восстановление пароля ────────────────────────────────

    #[Test]
    public function запрос_на_сброс_шлёт_письмо_со_ссылкой(): void
    {
        Notification::fake();

        $user = User::factory()->create(['email' => 'rustam@company.uz']);

        $this->post('/forgot-password', ['email' => 'rustam@company.uz'])
            ->assertSessionHasNoErrors();

        Notification::assertSentTo($user, ResetPassword::class);
    }

    /** NEG-06d: по ответу нельзя понять, зарегистрирован адрес или нет. */
    #[Test]
    public function ответ_одинаков_для_несуществующего_адреса(): void
    {
        Notification::fake();

        User::factory()->create(['email' => 'rustam@company.uz']);

        $exists = $this->post('/forgot-password', ['email' => 'rustam@company.uz']);
        $missing = $this->post('/forgot-password', ['email' => 'never@company.uz']);

        $exists->assertSessionHasNoErrors();
        $missing->assertSessionHasNoErrors();
        $this->assertSame($exists->getStatusCode(), $missing->getStatusCode());
    }

    #[Test]
    public function по_ссылке_из_письма_пароль_меняется(): void
    {
        Notification::fake();

        $user = User::factory()->create(['email' => 'rustam@company.uz']);
        $this->post('/forgot-password', ['email' => 'rustam@company.uz']);

        $token = null;
        Notification::assertSentTo($user, ResetPassword::class, function (ResetPassword $n) use (&$token): bool {
            $token = $n->token;

            return true;
        });

        $this->post('/reset-password', [
            'token' => $token,
            'email' => 'rustam@company.uz',
            'password' => 'НовыйПароль2026!',
            'password_confirmation' => 'НовыйПароль2026!',
        ])->assertRedirect('/login')->assertSessionHasNoErrors();

        $this->assertTrue(password_verify('НовыйПароль2026!', $user->fresh()->password));
    }

    #[Test]
    public function просроченный_токен_отклоняется_с_понятным_текстом(): void
    {
        User::factory()->create(['email' => 'rustam@company.uz']);

        $this->post('/reset-password', [
            'token' => 'заведомо-неверный-токен',
            'email' => 'rustam@company.uz',
            'password' => 'НовыйПароль2026!',
            'password_confirmation' => 'НовыйПароль2026!',
        ])->assertInvalid(['email' => 'устарела']);
    }

    #[Test]
    public function страница_сброса_открывается_по_токену(): void
    {
        $this->get('/reset-password/kakoy-to-token?email=rustam@company.uz')->assertOk();
    }
}
