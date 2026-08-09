<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;

/**
 * Блок главной страницы: порядок, тексты, видимость (§6.5 ТЗ).
 *
 * Заказчик просил именно это: менять очерёдность блоков и их тексты
 * без разработчика.
 */
#[Fillable(['key', 'name', 'eyebrow', 'heading', 'subheading', 'payload', 'is_visible', 'sort'])]
class LandingBlock extends Model
{
    protected function casts(): array
    {
        return ['payload' => 'array', 'is_visible' => 'boolean'];
    }

    /** @param Builder<self> $query */
    public function scopeVisible(Builder $query): void
    {
        $query->where('is_visible', true)->orderBy('sort');
    }
}
