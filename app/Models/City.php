<?php

declare(strict_types=1);

namespace App\Models;

use App\Models\Concerns\RefusesDeletionWhenReferenced;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class City extends Model
{
    use RefusesDeletionWhenReferenced;

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

    /** Резюме соискателей: по ним строится фильтр городов в разделе. */
    public function resumes(): HasMany
    {
        return $this->hasMany(Resume::class);
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

    public function companies(): HasMany
    {
        return $this->hasMany(Company::class);
    }

    /**
     * Что удерживает город от удаления.
     *
     * @return array<string, int>
     */
    public function references(): array
    {
        $counts = [
            'компании' => $this->companies()->count(),
            'объявления' => $this->listings()->count(),
        ];

        return array_filter($counts);
    }
}
