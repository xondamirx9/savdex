<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Привязанная карта. Хранится токен провайдера и последние четыре
 * цифры — полный номер площадке не передаётся вовсе.
 */
#[Fillable(['company_id', 'provider', 'token', 'brand', 'last4', 'expires', 'is_default'])]
class PaymentMethod extends Model
{
    protected $hidden = ['token'];

    protected function casts(): array
    {
        return ['is_default' => 'boolean'];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function masked(): string
    {
        return trim(($this->brand ?? 'Карта').' •••• '.$this->last4);
    }
}
