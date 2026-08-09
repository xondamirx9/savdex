<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Carbon;

/**
 * Дополнительное поле компании (§5.2 FR-COMP-02 ТЗ).
 * Позволяет добавлять данные без миграций — набор полей задаёт суперадмин.
 */
class CompanyAttribute extends Model
{
    protected $fillable = ['company_id', 'key', 'value', 'type'];

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    /** Значение, приведённое к объявленному типу. */
    public function typedValue(): mixed
    {
        return match ($this->type) {
            'number' => is_numeric($this->value) ? $this->value + 0 : null,
            'bool' => filter_var($this->value, FILTER_VALIDATE_BOOL),
            'date' => $this->value ? Carbon::parse($this->value) : null,
            'json' => json_decode((string) $this->value, true),
            default => $this->value,
        };
    }
}
