<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Поле, специфичное для категории: марка цемента, состав ткани.
 * Подставляется в мастер создания объявления автоматически.
 */
#[Fillable(['category_id', 'key', 'label', 'type', 'options', 'unit', 'is_required', 'sort'])]
class CategoryField extends Model
{
    protected function casts(): array
    {
        return ['options' => 'array', 'is_required' => 'boolean'];
    }

    public function category(): BelongsTo
    {
        return $this->belongsTo(Category::class);
    }
}
