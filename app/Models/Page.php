<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * Редактируемая страница: «О нас», «Контакты», оферта, политика.
 *
 * Ключ отделён от адреса: страница может переехать по другому URL,
 * а ссылки в коде обращаются к ней по ключу и остаются рабочими.
 */
#[Fillable([
    'key', 'slug', 'title', 'excerpt', 'body',
    'meta_title', 'meta_description', 'is_published', 'sort',
])]
class Page extends Model
{
    protected function casts(): array
    {
        return ['is_published' => 'boolean'];
    }

    public function faq(): HasMany
    {
        return $this->hasMany(FaqItem::class)->where('is_published', true)->orderBy('sort');
    }

    public function paragraphs(): array
    {
        return collect(preg_split('/\R{2,}/u', (string) $this->body))
            ->map(fn (string $p): string => trim($p))
            ->filter()
            ->values()
            ->all();
    }
}
