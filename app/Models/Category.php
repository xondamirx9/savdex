<?php

declare(strict_types=1);

namespace App\Models;

use Database\Factories\CategoryFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * Категория объявлений. Дерево на два уровня: раздел и подраздел.
 */
#[Fillable(['parent_id', 'slug', 'icon', 'sort', 'is_active'])]
class Category extends Model
{
    /** @use HasFactory<CategoryFactory> */
    use HasFactory;

    protected function casts(): array
    {
        return ['is_active' => 'boolean'];
    }

    public function parent(): BelongsTo
    {
        return $this->belongsTo(self::class, 'parent_id');
    }

    public function children(): HasMany
    {
        return $this->hasMany(self::class, 'parent_id')->orderBy('sort');
    }

    public function translations(): HasMany
    {
        return $this->hasMany(CategoryTranslation::class);
    }

    public function fields(): HasMany
    {
        return $this->hasMany(CategoryField::class)->orderBy('sort');
    }

    public function listings(): HasMany
    {
        return $this->hasMany(Listing::class);
    }

    /**
     * Название на текущем языке. Русский — запасной вариант: пустая
     * строка вместо названия категории выглядит как поломка каталога.
     */
    public function name(?string $locale = null): string
    {
        $locale ??= app()->getLocale();
        $translations = $this->relationLoaded('translations') ? $this->translations : $this->translations()->get();

        return $translations->firstWhere('locale', $locale)?->name
            ?? $translations->firstWhere('locale', 'ru')?->name
            ?? $this->slug;
    }
}
