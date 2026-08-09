<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class City extends Model
{
    protected $fillable = ['country_id', 'slug', 'lat', 'lng', 'sort', 'is_active'];

    protected function casts(): array
    {
        return ['is_active' => 'boolean', 'lat' => 'decimal:7', 'lng' => 'decimal:7'];
    }

    public function country(): BelongsTo
    {
        return $this->belongsTo(Country::class);
    }

    /** Объявления в городе — по ним строится фильтр каталога. */
    public function listings(): HasMany
    {
        return $this->hasMany(Listing::class);
    }

    public function translations(): HasMany
    {
        return $this->hasMany(CityTranslation::class);
    }

    public function name(?string $locale = null): string
    {
        $locale ??= app()->getLocale();

        return $this->translations->firstWhere('locale', $locale)?->name
            ?? $this->translations->firstWhere('locale', 'ru')?->name
            ?? $this->slug;
    }
}
