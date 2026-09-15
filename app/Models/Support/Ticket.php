<?php

declare(strict_types=1);

namespace App\Models\Support;

use App\Models\Company;
use App\Models\User;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * Обращение в поддержку.
 *
 * Автор хранится и ссылкой, и строками: обращение приходит и от того,
 * кто не смог войти, — а это как раз самые срочные обращения.
 */
#[Fillable([
    'subject', 'user_id', 'company_id', 'author_name', 'author_email',
    'assignee_id', 'status', 'channel', 'priority', 'last_reply_at', 'closed_at',
])]
class Ticket extends Model
{
    use HasFactory;
    use SoftDeletes;

    protected $table = 'support_tickets';

    public const STATUS_OPEN = 'open';

    public const STATUS_WORKING = 'working';

    public const STATUS_WAITING = 'waiting';

    public const STATUS_CLOSED = 'closed';

    /** @var array<string, string> */
    public const STATUSES = [
        self::STATUS_OPEN => 'Открыто',
        self::STATUS_WORKING => 'В работе',
        self::STATUS_WAITING => 'Ждёт ответа клиента',
        self::STATUS_CLOSED => 'Закрыто',
    ];

    /** @var array<string, string> */
    public const CHANNELS = [
        'form' => 'Форма на сайте',
        'email' => 'Почта',
        'phone' => 'Звонок',
        'chat' => 'Чат',
    ];

    /** @var array<string, string> */
    public const PRIORITIES = [
        'low' => 'Низкий',
        'normal' => 'Обычный',
        'high' => 'Срочный',
    ];

    protected function casts(): array
    {
        return [
            'last_reply_at' => 'datetime',
            'closed_at' => 'datetime',
        ];
    }

    protected static function booted(): void
    {
        /*
         * Дата закрытия ставится и снимается сама.
         *
         * Иначе переоткрытое обращение остаётся с датой закрытия, и
         * отчёт по срокам считает его закрытым дважды.
         */
        static::saving(static function (self $ticket): void {
            if ($ticket->status === self::STATUS_CLOSED && $ticket->closed_at === null) {
                $ticket->closed_at = now();
            }

            if ($ticket->status !== self::STATUS_CLOSED) {
                $ticket->closed_at = null;
            }
        });
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function assignee(): BelongsTo
    {
        return $this->belongsTo(User::class, 'assignee_id');
    }

    public function messages(): HasMany
    {
        return $this->hasMany(Message::class, 'ticket_id');
    }

    /** Открытые — всё, что ещё требует действий поддержки. */
    public function scopeOpen(Builder $query): void
    {
        $query->where('status', '!=', self::STATUS_CLOSED);
    }

    public function statusLabel(): string
    {
        return self::STATUSES[$this->status] ?? $this->status;
    }

    /** Кто обратился: из учётной записи, иначе из самого обращения. */
    public function author(): string
    {
        return $this->user?->name ?? $this->author_name ?? 'неизвестно';
    }

    public function authorEmail(): ?string
    {
        return $this->user?->email ?? $this->author_email;
    }
}
