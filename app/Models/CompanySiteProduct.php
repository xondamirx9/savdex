<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Facades\Storage;

/**
 * Товар мини-сайта: строка витрины компании на её собственной странице.
 *
 * Фотография меняется только загрузкой через кабинет, поэтому пути
 * к файлам не в #[Fillable].
 *
 * @property int $id
 * @property int $company_id
 * @property string $title
 * @property string|null $image_path
 * @property string|null $thumb_path
 */
#[Fillable(['company_id', 'title', 'description', 'price', 'currency', 'unit', 'sort'])]
class CompanySiteProduct extends Model
{
    /** Сколько товаров можно завести: витрина, а не каталог. */
    public const LIMIT = 60;

    protected function casts(): array
    {
        return ['price' => 'decimal:2', 'sort' => 'integer'];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    /** Миниатюра для карточки; null — фото нет или файл пропал. */
    public function thumbUrl(): ?string
    {
        $path = $this->thumb_path ?? $this->image_path;

        return $path !== null && Storage::disk('public')->exists($path) ? asset('storage/'.$path) : null;
    }
}
