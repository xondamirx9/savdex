<?php

declare(strict_types=1);

namespace App\Models;

use App\Models\Concerns\RefusesDeletionWhenReferenced;
use Database\Factories\CategoryFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Facades\DB;

/**
 * Категория объявлений. Дерево на два уровня: раздел и подраздел.
 *
 * С этапа 2 переноса категории правятся в разделе на Python
 * (python/savdex/catalogs/), здесь остались правила модели.
 */
#[Fillable(['parent_id', 'slug', 'icon', 'sort', 'is_active'])]
class Category extends Model
{
    /** @use HasFactory<CategoryFactory> */
    use HasFactory;

    use RefusesDeletionWhenReferenced;

    /** Кто ссылается на категорию: таблица и столбец => как назвать. */
    private const REFERENCES = [
        'подкатегории' => ['categories', 'parent_id'],
        'объявления' => ['listings', 'category_id'],
        'тендеры' => ['tenders', 'category_id'],
        'продвижения' => ['promotions', 'category_id'],
        'компании' => ['company_category', 'category_id'],
    ];

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
     * Что удерживает категорию от удаления.
     *
     * Раньше удаление ничем не было защищено, а внешние ключи ему не
     * мешают: подкатегории раздела молча становились разделами, у
     * объявлений, тендеров и продвижений категория обнулялась, привязки
     * компаний стирались каскадом.
     *
     * Считаются и удалённые в корзину строки: внешний ключ задел бы и
     * их, и восстановленное объявление вернулось бы без категории.
     *
     * @return array<string, int>
     */
    public function references(): array
    {
        $counts = [];

        foreach (self::REFERENCES as $label => [$table, $column]) {
            $counts[$label] = DB::table($table)->where($column, $this->getKey())->count();
        }

        return array_filter($counts);
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
