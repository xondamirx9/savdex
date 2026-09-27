<?php

declare(strict_types=1);

namespace App\Models;

use App\Models\Concerns\HasOwnTranslations;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Вопрос-ответ на странице «Помощь».
 *
 * Языки — свои поля и машинный перевод про запас, как у Page.
 */
#[Fillable(['page_id', 'question', 'question_i18n', 'answer', 'answer_i18n', 'sort', 'is_published'])]
class FaqItem extends Model
{
    use HasOwnTranslations;

    protected function casts(): array
    {
        return [
            'is_published' => 'boolean',
            'question_i18n' => 'array',
            'answer_i18n' => 'array',
        ];
    }

    public function page(): BelongsTo
    {
        return $this->belongsTo(Page::class);
    }
}
