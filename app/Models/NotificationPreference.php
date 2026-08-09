<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Настройка уведомлений пользователя по одному событию. */
#[Fillable(['user_id', 'event', 'email', 'telegram'])]
class NotificationPreference extends Model
{
    /** Порядок и подписи — как в разделе «Настройки» кабинета. */
    public const EVENTS = [
        'contact_unlocked' => 'Открыли мой контакт',
        'new_review' => 'Новый отзыв',
        'moderation' => 'Модерация объявления',
        'listing_expiring' => 'Объявление истекает',
        'digest' => 'Дайджест по подпискам',
    ];

    protected function casts(): array
    {
        return ['email' => 'boolean', 'telegram' => 'boolean'];
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
}
