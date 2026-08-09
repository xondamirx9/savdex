<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Событие в ленте кабинета. */
#[Fillable(['company_id', 'type', 'tone', 'message', 'url', 'subject_type', 'subject_id', 'read_at'])]
class ActivityEvent extends Model
{
    protected function casts(): array
    {
        return ['read_at' => 'datetime'];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }
}
