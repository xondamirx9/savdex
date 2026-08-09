<?php

declare(strict_types=1);

namespace App\Models;

use Database\Factories\UserNotificationFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Уведомление пользователя.
 *
 * Отличается от ActivityEvent адресатом: событие принадлежит компании
 * и видно всем её сотрудникам, уведомление — конкретному человеку
 * и имеет состояние прочтения.
 */
#[Fillable([
    'user_id', 'company_id', 'type', 'tone', 'title', 'body', 'url',
    'subject_type', 'subject_id', 'sent_by', 'is_broadcast', 'read_at',
])]
class UserNotification extends Model
{
    /** @use HasFactory<UserNotificationFactory> */
    use HasFactory;

    public const TYPE_BROADCAST = 'broadcast';

    protected function casts(): array
    {
        return ['read_at' => 'datetime', 'is_broadcast' => 'boolean'];
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function sender(): BelongsTo
    {
        return $this->belongsTo(User::class, 'sent_by');
    }

    /** @param Builder<self> $query */
    public function scopeUnread(Builder $query): void
    {
        $query->whereNull('read_at');
    }

    public function markRead(): void
    {
        if ($this->read_at === null) {
            $this->forceFill(['read_at' => now()])->save();
        }
    }

    /**
     * Создать уведомление для пользователя.
     *
     * Имя deliver, а не push: push уже занят Eloquent — он сохраняет
     * модель вместе со связями, и переопределить его статическим
     * нельзя (fatal error на уровне PHP).
     *
     * Настройки каналов отключают почту и Telegram, но не саму запись:
     * иначе в кабинете исчезает история, и человек не понимает, почему
     * «открыли контакт» нигде не отражается.
     */
    public static function deliver(User $user, array $attributes): self
    {
        return self::create([
            'user_id' => $user->id,
            'company_id' => $user->company_id,
            ...$attributes,
        ]);
    }
}
