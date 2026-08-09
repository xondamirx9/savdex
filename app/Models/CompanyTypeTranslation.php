<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

#[Fillable(['company_type_id', 'locale', 'name'])]
class CompanyTypeTranslation extends Model
{
    public function companyType(): BelongsTo
    {
        return $this->belongsTo(CompanyType::class);
    }
}
