<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Рассылка уведомлений от администратора.
 *
 * Хранится отдельно от персональных уведомлений: нужна история отправок
 * с охватом, а собирать её из тысяч одинаковых строк — лишняя работа
 * при каждом открытии раздела.
 */
#[Fillable([
    'sent_by', 'title', 'body', 'url', 'tone',
    'audience', 'audience_value', 'recipients_count', 'sent_at',
])]
class Broadcast extends Model
{
    /** Сегменты получателей. Ключ — значение поля audience. */
    public const AUDIENCES = [
        'all' => 'Все пользователи',
        'plan' => 'Компании на тарифе',
        'verified' => 'Проверенные компании',
        'unverified' => 'Непроверенные компании',
        'no_company' => 'Без компании',
    ];

    protected function casts(): array
    {
        return ['sent_at' => 'datetime'];
    }

    public function sender(): BelongsTo
    {
        return $this->belongsTo(User::class, 'sent_by');
    }

    public function audienceLabel(): string
    {
        $label = self::AUDIENCES[$this->audience] ?? $this->audience;

        return $this->audience === 'plan' && $this->audience_value !== null
            ? $label.' '.$this->audience_value
            : $label;
    }
}
