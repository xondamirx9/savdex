<?php

declare(strict_types=1);

namespace App\Models;

use App\Notifications\VerifyEmailCode;
use App\Support\AdminAccess;
use App\Support\EmailVerificationCode;
use Database\Factories\UserFactory;
use Filament\Models\Contracts\FilamentUser;
use Filament\Panel;
use Illuminate\Contracts\Auth\MustVerifyEmail;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Attributes\Hidden;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;

/**
 * Пользователь — сотрудник компании либо администратор площадки.
 *
 * Реализует MustVerifyEmail: до подтверждения почты кабинет доступен,
 * но публикация и раскрытие контактов заблокированы (§5.1 FR-AUTH-02 ТЗ).
 * Полная блокировка на этом шаге убила бы конверсию регистрации.
 */
#[Fillable([
    'company_id', 'name', 'email', 'password', 'phone', 'locale',
    'company_role', 'is_admin', 'admin_role', 'admin_permissions', 'must_change_password', 'status',
    'telegram_chat_id', 'telegram_username', 'telegram_linked_at',
])]
#[Hidden(['password', 'remember_token', 'two_factor_secret'])]
class User extends Authenticatable implements FilamentUser, MustVerifyEmail
{
    /** @use HasFactory<UserFactory> */
    use HasFactory;

    use Notifiable;
    use SoftDeletes;

    public const ROLE_OWNER = 'owner';

    public const ROLE_MANAGER = 'manager';

    /**
     * Роли в админке. Сам список и матрица прав — в AdminAccess.
     *
     * Здесь оставлены только два имени, на которые ссылается код вне
     * матрицы: суперадмин упоминается в проверках «последний владелец»,
     * модератор — роль по умолчанию у команды создания администратора.
     */
    public const ADMIN_MODERATOR = AdminAccess::MODERATOR;

    public const ADMIN_SUPERADMIN = AdminAccess::SUPERADMIN;

    public const ADMIN_ROLES = AdminAccess::ROLES;

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'phone_verified_at' => 'datetime',
            'telegram_linked_at' => 'datetime',
            'two_factor_confirmed_at' => 'datetime',
            'last_login_at' => 'datetime',
            'password' => 'hashed',
            'is_admin' => 'boolean',
            'admin_permissions' => 'array',
            'must_change_password' => 'boolean',
        ];
    }

    /**
     * Письмо подтверждения — своё, с кодом для ввода на сайте вдобавок
     * к подписанной ссылке. Метод зовёт и слушатель события Registered,
     * и кнопка «Отправить повторно» — код выпускается в одном месте.
     *
     * Ошибка отправки логируется, а не роняет запрос: регистрация уже
     * падала с 500 после создания пользователя (см. EmailVerificationTest),
     * и недоступный SMTP не должен повторить тот дефект — человек
     * запросит письмо повторно с экрана подтверждения.
     */
    public function sendEmailVerificationNotification(): void
    {
        try {
            $this->notify(new VerifyEmailCode(EmailVerificationCode::issue($this)));
        } catch (\Throwable $e) {
            report($e);
        }
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function notificationPreferences(): HasMany
    {
        return $this->hasMany(NotificationPreference::class);
    }

    /**
     * Уведомления пользователя внутри площадки.
     *
     * Имя alerts, а не notifications: последнее занято трейтом
     * Notifiable. Переопределение ломало доставку штатных уведомлений
     * Laravel — Filament шлёт через $user->notify() свои сообщения
     * о готовности выгрузки, и они падали на MassAssignmentException,
     * пытаясь записаться в нашу таблицу с чужим набором полей.
     */
    public function alerts(): HasMany
    {
        return $this->hasMany(UserNotification::class)->latest();
    }

    public function isOwner(): bool
    {
        return $this->company_role === self::ROLE_OWNER;
    }

    /**
     * Может ли пользователь совершать действия, требующие подтверждённой почты
     * и активной компании. Используется политиками публикации и раскрытия контактов.
     */
    public function canAct(): bool
    {
        return $this->hasVerifiedEmail()
            && $this->status === 'active'
            && ! $this->must_change_password
            && ! ($this->company?->isBlocked() ?? false);
    }

    /**
     * Доступ в админ-панель Filament.
     *
     * Проверка именно здесь, а не только скрытием пунктов меню:
     * NEG-26e из QA.md требует, чтобы модератор не мог открыть биллинг
     * по прямой ссылке.
     */
    public function canAccessPanel(Panel $panel): bool
    {
        return $this->is_admin && $this->status === 'active';
    }

    /**
     * Полный доступ: биллинг, настройки, выдача доступов, импорт данных.
     *
     * Единственная роль, которой разрешено всё, включая разделы, которых
     * ещё не существует. Иначе каждый новый раздел пришлось бы отдельно
     * выдавать владельцу системы, и однажды про это забудут.
     */
    public function isSuperadmin(): bool
    {
        return $this->is_admin && $this->admin_role === self::ADMIN_SUPERADMIN;
    }

    /**
     * Есть ли право — главный вопрос, который задаёт панель.
     *
     * Заблокированный сотрудник не имеет прав вовсе, какой бы ни была
     * роль: отозвать доступ одним полем должно получаться, не разбираясь
     * в том, что этой роли когда-то выдали.
     */
    public function hasAdminAbility(string $ability): bool
    {
        if (! $this->is_admin || $this->status !== 'active') {
            return false;
        }

        if ($this->isSuperadmin()) {
            return true;
        }

        return in_array($ability, $this->adminAbilities(), true);
    }

    /**
     * Итоговый набор: права роли плюс выданные лично, минус отозванные.
     *
     * Отзыв применяется последним и потому сильнее выдачи. Так «отобрать»
     * работает предсказуемо: одно и то же право, попавшее в оба списка,
     * не достанется никому — а спорную пару разрешать в пользу доступа
     * было бы ровно тем поведением, которого от защиты не ждут.
     *
     * @return list<string>
     */
    public function adminAbilities(): array
    {
        $permissions = $this->admin_permissions ?? [];

        $granted = array_merge(
            AdminAccess::abilitiesFor($this->admin_role),
            array_filter((array) ($permissions['grant'] ?? []), 'is_string'),
        );

        $revoked = array_filter((array) ($permissions['revoke'] ?? []), 'is_string');

        return array_values(array_diff(array_unique($granted), $revoked));
    }

    /**
     * Ограничен ли раздел своими записями.
     *
     * Право, выданное лично, область видимости не расширяет: выдать
     * продавцу «сделки» поштучно и нечаянно открыть ему чужие — не то,
     * чего ждут от галочки в списке прав.
     */
    public function adminScopeIsOwn(string $section): bool
    {
        return ! $this->isSuperadmin() && AdminAccess::scopeIsOwn($this->admin_role, $section);
    }

    public function adminRoleLabel(): ?string
    {
        if (! $this->is_admin) {
            return null;
        }

        return self::ADMIN_ROLES[$this->admin_role] ?? 'Роль не назначена';
    }
}
