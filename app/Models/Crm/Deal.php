<?php

declare(strict_types=1);

namespace App\Models\Crm;

use App\Models\Company;
use App\Models\User;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\MorphMany;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * Сделка — работа с клиентом по конкретной сумме.
 *
 * Сумма хранится целым числом: сумы без копеек, а дробное хранение денег
 * однажды покажет 1 999 999.99 там, где должно стоять два миллиона.
 */
#[Fillable([
    'title', 'company_id', 'contact_id', 'lead_id', 'owner_id',
    'amount', 'currency', 'stage', 'expected_close_at', 'closed_at',
    'lost_reason', 'note',
])]
class Deal extends Model
{
    use HasFactory;
    use SoftDeletes;

    protected $table = 'crm_deals';

    public const STAGE_NEW = 'new';

    public const STAGE_NEGOTIATION = 'negotiation';

    public const STAGE_PROPOSAL = 'proposal';

    public const STAGE_WON = 'won';

    public const STAGE_LOST = 'lost';

    /** @var array<string, string> */
    public const STAGES = [
        self::STAGE_NEW => 'Новая',
        self::STAGE_NEGOTIATION => 'Переговоры',
        self::STAGE_PROPOSAL => 'Предложение отправлено',
        self::STAGE_WON => 'Выиграна',
        self::STAGE_LOST => 'Проиграна',
    ];

    /** @var array<string, string> */
    public const CURRENCIES = [
        'UZS' => 'сум',
        'USD' => '$',
        'EUR' => '€',
        'RUB' => '₽',
    ];

    protected function casts(): array
    {
        return [
            'amount' => 'integer',
            'expected_close_at' => 'date',
            'closed_at' => 'datetime',
        ];
    }

    protected static function booted(): void
    {
        /*
         * Дата закрытия ставится сама.
         *
         * Просить человека отметить и этап, и дату — значит получить
         * выигранные сделки без даты и отчёт, который не считается.
         */
        static::saving(static function (self $deal): void {
            $closed = in_array($deal->stage, [self::STAGE_WON, self::STAGE_LOST], true);

            if ($closed && $deal->closed_at === null) {
                $deal->closed_at = now();
            }

            if (! $closed) {
                $deal->closed_at = null;
            }
        });
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function contact(): BelongsTo
    {
        return $this->belongsTo(Contact::class);
    }

    public function lead(): BelongsTo
    {
        return $this->belongsTo(Lead::class);
    }

    public function owner(): BelongsTo
    {
        return $this->belongsTo(User::class, 'owner_id');
    }

    public function tasks(): MorphMany
    {
        return $this->morphMany(Task::class, 'subject');
    }

    public function communications(): MorphMany
    {
        return $this->morphMany(Communication::class, 'subject');
    }

    public function scopeOpen(Builder $query): void
    {
        $query->whereNotIn('stage', [self::STAGE_WON, self::STAGE_LOST]);
    }

    public function stageLabel(): string
    {
        return self::STAGES[$this->stage] ?? $this->stage;
    }

    /** «46 386 000 сум» — с пробелами, иначе цифры не читаются. */
    public function money(): string
    {
        return number_format($this->amount, 0, ',', ' ')
            .' '.(self::CURRENCIES[$this->currency] ?? $this->currency);
    }
}
