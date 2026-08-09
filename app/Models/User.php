<?php

declare(strict_types=1);

namespace App\Models;

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
    'company_role', 'is_admin', 'admin_role', 'must_change_password', 'status',
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

    /** Роли в админке (§6.3 ТЗ). */
    public const ADMIN_MODERATOR = 'moderator';

    public const ADMIN_SUPERADMIN = 'superadmin';

    public const ADMIN_ROLES = [
        self::ADMIN_MODERATOR => 'Модератор',
        self::ADMIN_SUPERADMIN => 'Суперадмин',
    ];

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'phone_verified_at' => 'datetime',
            'two_factor_confirmed_at' => 'datetime',
            'last_login_at' => 'datetime',
            'password' => 'hashed',
            'is_admin' => 'boolean',
            'must_change_password' => 'boolean',
        ];
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
     * Роль по умолчанию — модератор: администратор без явно указанной
     * роли не должен случайно получить право менять тарифы и выгружать
     * базу. Права расширяют осознанно, а не по умолчанию.
     */
    public function isSuperadmin(): bool
    {
        return $this->is_admin && $this->admin_role === self::ADMIN_SUPERADMIN;
    }

    /** Модерация: объявления, компании, жалобы, отзывы. */
    public function isModerator(): bool
    {
        return $this->is_admin && in_array(
            $this->admin_role,
            [self::ADMIN_MODERATOR, self::ADMIN_SUPERADMIN],
            true,
        );
    }

    public function adminRoleLabel(): ?string
    {
        return $this->is_admin
            ? (self::ADMIN_ROLES[$this->admin_role] ?? 'Модератор')
            : null;
    }
}
