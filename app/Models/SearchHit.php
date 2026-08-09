<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Поисковый запрос, по которому показывались объявления компании. */
#[Fillable(['company_id', 'query', 'date', 'impressions', 'clicks'])]
class SearchHit extends Model
{
    protected function casts(): array
    {
        return ['date' => 'date'];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }
}
