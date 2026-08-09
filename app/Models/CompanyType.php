<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * Тип компании: производитель, импортёр, дистрибьютор и так далее.
 *
 * Справочник, а не константа: заказчик добавляет типы по мере
 * знакомства с рынком, и ждать релиза ради строки «Логистика»
 * незачем.
 */
#[Fillable(['code', 'sort', 'is_active'])]
class CompanyType extends Model
{
    protected function casts(): array
    {
        return ['is_active' => 'boolean'];
    }

    public function translations(): HasMany
    {
        return $this->hasMany(CompanyTypeTranslation::class);
    }

    public function companies(): HasMany
    {
        return $this->hasMany(Company::class, 'type', 'code');
    }

    /** @param Builder<self> $query */
    public function scopeActive(Builder $query): void
    {
        $query->where('is_active', true)->orderBy('sort');
    }

    /**
     * Название на текущем языке. Русский — запасной: пустая строка
     * вместо типа компании выглядит как поломка формы.
     */
    public function name(?string $locale = null): string
    {
        $locale ??= app()->getLocale();

        $translations = $this->relationLoaded('translations')
            ? $this->translations
            : $this->translations()->get();

        return $translations->firstWhere('locale', $locale)?->name
            ?? $translations->firstWhere('locale', 'ru')?->name
            ?? $this->code;
    }

    /**
     * Справочник для форм: код => название.
     *
     * @return array<string, string>
     */
    public static function options(): array
    {
        return self::query()
            ->active()
            ->with('translations')
            ->get()
            ->mapWithKeys(fn (self $type): array => [$type->code => $type->name()])
            ->all();
    }
}
