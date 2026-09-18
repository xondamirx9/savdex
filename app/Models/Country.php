<?php

declare(strict_types=1);

namespace App\Models;

use App\Models\Concerns\RefusesDeletionWhenReferenced;
use Collator;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Country extends Model
{
    use RefusesDeletionWhenReferenced;

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

    public function companies(): HasMany
    {
        return $this->hasMany(Company::class);
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

    /**
     * Страны для списка выбора: основные рынки сверху, остальные
     * по алфавиту.
     *
     * Порядок из колонки sort сам по себе список уже не держит:
     * стран три десятка, и направления расширения стоят в нём
     * в порядке добавления в базу — то есть случайно для того,
     * кто ищет свою страну. Внутри одного sort страны выстраиваются
     * по названию, а «по алфавиту» в каждом языке своё: сравнивает
     * их ICU (Collator) по правилам языка страницы — иначе турецкая
     * «İ» уезжает в конец списка, а китайские названия встают
     * по номерам символов вместо чтения.
     *
     * Выключенные страны в списке не нужны никому, кроме админки:
     * там страна, снятая с публикации, обязана оставаться вариантом —
     * иначе форма компании, стоящей на ней, молча обнулит поле.
     *
     * @return Collection<int, self>
     */
    public static function listed(?string $locale = null, bool $withInactive = false): Collection
    {
        $locale ??= app()->getLocale();

        // intl стоит в образе, но обязательным для запуска сайта
        // расширение не делаем: без него список просто выстроится
        // по кодовым позициям символов
        $collator = class_exists(Collator::class) ? new Collator($locale) : null;

        return self::query()
            ->unless($withInactive, fn ($q) => $q->where('is_active', true))
            ->with('translations')
            ->get()
            ->sort(function (self $a, self $b) use ($locale, $collator): int {
                if ($a->sort !== $b->sort) {
                    return $a->sort <=> $b->sort;
                }

                $left = $a->name($locale);
                $right = $b->name($locale);

                return $collator !== null
                    ? (int) $collator->compare($left, $right)
                    : $left <=> $right;
            })
            ->values();
    }

    public function tenders(): HasMany
    {
        return $this->hasMany(Tender::class);
    }

    /**
     * Что удерживает страну от удаления.
     *
     * Города считаются наравне с компаниями: внешний ключ у них
     * каскадный, и удаление страны увело бы их за собой без вопросов.
     *
     * @return array<string, int>
     */
    public function references(): array
    {
        $counts = [
            'города' => $this->cities()->count(),
            'компании' => $this->companies()->count(),
            'тендеры' => $this->tenders()->count(),
        ];

        return array_filter($counts);
    }
}
