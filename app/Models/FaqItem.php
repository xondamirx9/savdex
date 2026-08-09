<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Вопрос-ответ на странице помощи. */
#[Fillable(['page_id', 'question', 'answer', 'sort', 'is_published'])]
class FaqItem extends Model
{
    protected function casts(): array
    {
        return ['is_published' => 'boolean'];
    }

    public function page(): BelongsTo
    {
        return $this->belongsTo(Page::class);
    }
}
