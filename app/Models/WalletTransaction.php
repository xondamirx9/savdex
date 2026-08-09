<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Движение по кошельку. Остаток обязан быть выводим из истории —
 * иначе спор «у меня списали лишнее» нечем закрыть.
 */
#[Fillable([
    'company_id', 'user_id', 'kind', 'amount', 'balance_after',
    'reason', 'subject_type', 'subject_id', 'comment',
])]
class WalletTransaction extends Model
{
    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }
}
