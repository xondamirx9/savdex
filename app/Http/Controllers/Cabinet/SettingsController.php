<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\NotificationPreference;
use App\Services\Messaging\TelegramGateway;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Hash;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Настройки: уведомления, профиль, безопасность, удаление аккаунта.
 */
class SettingsController extends Controller
{
    public function index(Request $request): Response
    {
        $user = $request->user();

        $saved = $user->notificationPreferences()->get()->keyBy('event');

        return Inertia::render('cabinet/Settings', [
            'profile' => [
                'name' => $user->name,
                'email' => $user->email,
                'phone' => $user->phone,
                'locale' => $user->locale,
                'email_verified' => $user->hasVerifiedEmail(),
                'phone_verified' => $user->phone_verified_at !== null,
            ],

            /*
             * Значения по умолчанию проставляются здесь, а не строками
             * в базе при регистрации: список событий будет расти,
             * и дописывать миграцию под каждое новое — лишняя работа.
             */
            'notifications' => collect(NotificationPreference::EVENTS)
                ->map(fn (string $label, string $event): array => [
                    'event' => $event,
                    'label' => $label,
                    'email' => $saved->get($event)?->email ?? true,
                    'telegram' => $saved->get($event)?->telegram ?? false,
                ])
                ->values(),

            /*
             * Telegram: показываем, привязан ли, и умеет ли площадка
             * привязывать вообще. Без бота раздел не показывается —
             * кнопка, ведущая в никуда, хуже её отсутствия.
             */
            'telegram' => [
                'available' => app(TelegramGateway::class)->configured(),
                'linked' => $user->telegram_chat_id !== null,
                'username' => $user->telegram_username,
            ],

            'security' => [
                'two_factor' => $user->two_factor_confirmed_at !== null,
                'last_login_at' => $user->last_login_at?->translatedFormat('d.m.Y, H:i'),
                'last_login_ip' => $user->last_login_ip,
            ],

            'is_owner' => $user->isOwner(),
        ]);
    }

    public function notifications(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'notifications' => ['required', 'array'],
            'notifications.*.event' => ['required', 'string', 'in:'.implode(',', array_keys(NotificationPreference::EVENTS))],
            'notifications.*.email' => ['boolean'],
            'notifications.*.telegram' => ['boolean'],
        ]);

        foreach ($data['notifications'] as $row) {
            $request->user()->notificationPreferences()->updateOrCreate(
                ['event' => $row['event']],
                ['email' => (bool) ($row['email'] ?? false), 'telegram' => (bool) ($row['telegram'] ?? false)],
            );
        }

        return back()->with('success', __('ui.messages.settings.notifications_saved'));
    }

    public function profile(Request $request): RedirectResponse
    {
        $user = $request->user();

        $data = $request->validate([
            'name' => ['required', 'string', 'min:2', 'max:120'],
            'phone' => ['required', 'string', 'regex:/^\+?\d[\d\s\-()]{8,17}$/'],
            'locale' => ['required', 'in:ru,uz,en,zh,tr'],
        ], [
            'name.required' => __('ui.messages.settings.name_required'),
            'phone.regex' => __('ui.messages.phone_format'),
        ]);

        // Смена номера сбрасывает подтверждение: подтверждён был старый
        if ($data['phone'] !== $user->phone) {
            $user->phone_verified_at = null;
        }

        $user->fill($data)->save();

        // Язык хранится и в сессии — иначе интерфейс переключится
        // только при следующем входе
        $request->session()->put('locale', $data['locale']);

        return back()->with('success', __('ui.messages.settings.profile_saved'));
    }

    /**
     * Удаление аккаунта.
     *
     * Пароль спрашивается обязательно: чужой незаблокированный ноутбук —
     * самый частый сценарий, а действие необратимо для пользователя.
     * Объявления снимаются, история платежей остаётся по требованию закона.
     */
    public function destroy(Request $request): RedirectResponse
    {
        $request->validate([
            'password' => ['required', 'string'],
        ], [
            'password.required' => __('ui.messages.settings.password_confirm'),
        ]);

        $user = $request->user();

        if (! Hash::check($request->string('password')->toString(), $user->password)) {
            return back()->withErrors(['password' => __('ui.messages.settings.password_wrong')]);
        }

        if ($user->isOwner() && $user->company !== null) {
            $user->company->activeListings()->update(['status' => 'archived']);
        }

        Auth::logout();
        $user->delete();

        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect('/')->with('success', __('ui.messages.settings.account_deleted'));
    }
}
