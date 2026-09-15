<?php

declare(strict_types=1);

namespace App\Models\Crm;

use App\Models\Company;
use App\Models\User;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * Контакт — человек, с которым ведут работу.
 *
 * Отдельно от User: у контакта может не быть регистрации на площадке,
 * а у компании контактов несколько — снабженец, бухгалтер, директор.
 */
#[Fillable([
    'company_id', 'name', 'position', 'phone', 'email', 'telegram', 'note', 'created_by',
])]
class Contact extends Model
{
    use HasFactory;
    use SoftDeletes;

    protected $table = 'crm_contacts';

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    public function leads(): HasMany
    {
        return $this->hasMany(Lead::class, 'contact_id');
    }

    public function deals(): HasMany
    {
        return $this->hasMany(Deal::class, 'contact_id');
    }

    /** «Иван Петров, снабженец» — одной строкой для списков и заголовков. */
    public function label(): string
    {
        return $this->position !== null && $this->position !== ''
            ? "{$this->name}, {$this->position}"
            : $this->name;
    }
}
