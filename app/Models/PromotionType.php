<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * Инструмент продвижения: поднятие, ТОП категории, срочно и прочее.
 *
 * slots ограничивает число одновременных мест. Без ограничения
 * продвижение продаётся бесконечно и перестаёт работать у всех сразу.
 */
#[Fillable([
    'code', 'name', 'description', 'effect_hint', 'cost_units',
    'duration_days', 'slots', 'badge', 'icon', 'sort', 'is_active',
])]
class PromotionType extends Model
{
    protected function casts(): array
    {
        return ['is_active' => 'boolean'];
    }

    public function promotions(): HasMany
    {
        return $this->hasMany(Promotion::class);
    }

    /** Сколько мест занято прямо сейчас. */
    public function takenSlots(?int $categoryId = null): int
    {
        return $this->promotions()
            ->where('status', 'active')
            ->when($categoryId !== null, fn ($q) => $q->where('category_id', $categoryId))
            ->count();
    }

    public function hasFreeSlot(?int $categoryId = null): bool
    {
        return $this->slots === null || $this->takenSlots($categoryId) < $this->slots;
    }

    public function costLabel(): string
    {
        $units = $this->cost_units.' ед.';

        return $this->duration_days > 0
            ? $units.' / '.$this->duration_days.' дн.'
            : $units.' разово';
    }
}
