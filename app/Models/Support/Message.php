<?php

declare(strict_types=1);

namespace App\Models\Support;

use App\Models\User;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Сообщение в обращении.
 *
 * Внутренняя заметка отделена от ответа клиенту флагом, а не
 * договорённостью: без этого внутренние замечания однажды уедут тому,
 * о ком они написаны.
 */
#[Fillable([
    'ticket_id', 'author_id', 'from_staff', 'is_internal', 'body', 'attachments',
])]
class Message extends Model
{
    use HasFactory;

    protected $table = 'support_messages';

    protected function casts(): array
    {
        return [
            'from_staff' => 'boolean',
            'is_internal' => 'boolean',
            'attachments' => 'array',
        ];
    }

    public function ticket(): BelongsTo
    {
        return $this->belongsTo(Ticket::class, 'ticket_id');
    }

    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class, 'author_id');
    }

    /** То, что видит клиент: всё, кроме внутренних заметок. */
    public function scopeVisibleToClient(Builder $query): void
    {
        $query->where('is_internal', false);
    }
}
