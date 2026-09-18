<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Картинка баннера под отдельный язык. */
#[Fillable(['banner_id', 'locale', 'image_path', 'image_mobile_path'])]
class BannerImage extends Model
{
    public function banner(): BelongsTo
    {
        return $this->belongsTo(Banner::class);
    }
}
