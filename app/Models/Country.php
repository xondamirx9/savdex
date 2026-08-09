<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Country extends Model
{
    protected $fillable = ['code', 'phone_code', 'currency_code', 'sort', 'is_active'];

    protected function casts(): array
    {
        return ['is_active' => 'boolean', 'sort' => 'integer'];
    }

    /**
     * Код страны всегда в нижнем регистре.
     *
     * Уникальность в базе регистрозависима, поэтому firstOrCreate(['code' => 'UZ'])
     * заводил вторую страну рядом с существующей 'uz'. В списке при
     * регистрации было два «Узбекистана», и половина компаний уезжала
     * в дубль, у которого нет ни одного города.
     */
    protected static function booted(): void
    {
        static::saving(function (self $country): void {
            $country->code = mb_strtolower(trim((string) $country->code));
        });
    }

    public function cities(): HasMany
    {
        return $this->hasMany(City::class);
    }

    public function translations(): HasMany
    {
        return $this->hasMany(CountryTranslation::class);
    }

    /** Название на текущем языке, с откатом на русский. */
    public function name(?string $locale = null): string
    {
        $locale ??= app()->getLocale();

        return $this->translations->firstWhere('locale', $locale)?->name
            ?? $this->translations->firstWhere('locale', 'ru')?->name
            ?? $this->code;
    }
}
