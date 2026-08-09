<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

#[Fillable(['listing_id', 'key', 'value'])]
class ListingAttribute extends Model
{
    public function listing(): BelongsTo
    {
        return $this->belongsTo(Listing::class);
    }
}
