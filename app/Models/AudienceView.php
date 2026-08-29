<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Просмотр страниц компании с указанием зрителя.
 *
 * Пишется из StatsRecorder только для авторизованных посетителей
 * с компанией; дедупликация — та же получасовая, что и у счётчиков
 * просмотров, поэтому обновление страницы новых строк не плодит.
 */
#[Fillable(['target_company_id', 'viewer_company_id', 'listing_id'])]
class AudienceView extends Model
{
    public function viewer(): BelongsTo
    {
        return $this->belongsTo(Company::class, 'viewer_company_id');
    }

    public function listing(): BelongsTo
    {
        return $this->belongsTo(Listing::class);
    }
}
