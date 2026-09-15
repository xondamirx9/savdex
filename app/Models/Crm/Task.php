<?php

declare(strict_types=1);

namespace App\Models\Crm;

use App\Models\User;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\MorphTo;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * Задача — что сделать и к какому сроку.
 *
 * Привязка полиморфная: задача бывает и по лиду, и по сделке, и сама
 * по себе. Отдельная колонка под каждый случай означала бы, что две
 * из трёх всегда пусты.
 */
#[Fillable([
    'title', 'description', 'assignee_id', 'created_by',
    'due_at', 'done_at', 'subject_type', 'subject_id',
])]
class Task extends Model
{
    use HasFactory;
    use SoftDeletes;

    protected $table = 'crm_tasks';

    protected function casts(): array
    {
        return [
            'due_at' => 'datetime',
            'done_at' => 'datetime',
        ];
    }

    public function assignee(): BelongsTo
    {
        return $this->belongsTo(User::class, 'assignee_id');
    }

    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    public function subject(): MorphTo
    {
        return $this->morphTo();
    }

    public function scopeOpen(Builder $query): void
    {
        $query->whereNull('done_at');
    }

    public function isDone(): bool
    {
        return $this->done_at !== null;
    }

    /**
     * Просрочена ли задача.
     *
     * Выполненная задача просроченной не считается, даже если её сделали
     * позже срока: список «горит» должен показывать то, что ещё требует
     * действий, а не упрекать за прошлое.
     */
    public function isOverdue(): bool
    {
        return ! $this->isDone()
            && $this->due_at !== null
            && $this->due_at->isPast();
    }
}
