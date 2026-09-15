<?php

declare(strict_types=1);

namespace App\Models\Crm;

use App\Models\User;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\MorphTo;

/**
 * Коммуникация — запись состоявшегося разговора.
 *
 * Заводится руками: интеграции с почтой и телефонией пока нет. Но
 * история переговоров нужна уже сейчас — иначе она живёт в голове
 * одного продавца и уходит вместе с ним.
 *
 * Мягкого удаления нет намеренно: запись разговора либо была, либо
 * нет. «Удалённая, но восстановимая» история переговоров — это история,
 * которой нельзя верить.
 */
#[Fillable([
    'type', 'happened_at', 'summary', 'body',
    'author_id', 'contact_id', 'subject_type', 'subject_id',
])]
class Communication extends Model
{
    use HasFactory;

    protected $table = 'crm_communications';

    /** @var array<string, string> */
    public const TYPES = [
        'call' => 'Звонок',
        'email' => 'Письмо',
        'meeting' => 'Встреча',
        'message' => 'Сообщение',
    ];

    protected function casts(): array
    {
        return ['happened_at' => 'datetime'];
    }

    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class, 'author_id');
    }

    public function contact(): BelongsTo
    {
        return $this->belongsTo(Contact::class);
    }

    public function subject(): MorphTo
    {
        return $this->morphTo();
    }

    public function typeLabel(): string
    {
        return self::TYPES[$this->type] ?? $this->type;
    }
}
