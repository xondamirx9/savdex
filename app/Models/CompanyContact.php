<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Attributes\Scope;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Контакт компании: телефон, почта, мессенджер или сайт.
 *
 * У компании их может быть несколько — отдел продаж, склад, бухгалтерия.
 * Значение скрыто до оплаты раскрытия контактов (§5.6 ТЗ), наружу
 * отдаётся только маскированный вид.
 */
#[Fillable([
    'company_id', 'type', 'value', 'label', 'contact_person',
    'is_primary', 'is_public', 'sort_order',
])]
class CompanyContact extends Model
{
    use HasFactory;

    public const TYPE_PHONE = 'phone';

    public const TYPE_EMAIL = 'email';

    public const TYPE_TELEGRAM = 'telegram';

    public const TYPE_WHATSAPP = 'whatsapp';

    public const TYPE_WEBSITE = 'website';

    /** Сайт компании — не контакт для связи, его скрывать незачем. */
    public const PUBLIC_TYPES = [self::TYPE_WEBSITE];

    /** Типы контактов с подписями для форм и фильтров. */
    public const TYPES = [
        self::TYPE_PHONE => 'Телефон',
        self::TYPE_EMAIL => 'Почта',
        self::TYPE_TELEGRAM => 'Telegram',
        self::TYPE_WHATSAPP => 'WhatsApp',
        self::TYPE_WEBSITE => 'Сайт',
    ];

    public function typeLabel(): string
    {
        return self::TYPES[$this->type] ?? $this->type;
    }

    protected function casts(): array
    {
        return [
            'is_primary' => 'boolean',
            'is_public' => 'boolean',
            'sort_order' => 'integer',
        ];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    #[Scope]
    protected function visible(Builder $query): void
    {
        $query->where('is_public', true);
    }

    #[Scope]
    protected function ofType(Builder $query, string $type): void
    {
        $query->where('type', $type);
    }

    /** Порядок показа: основной первым, дальше по заданной сортировке. */
    #[Scope]
    protected function ordered(Builder $query): void
    {
        $query->orderByDesc('is_primary')->orderBy('sort_order')->orderBy('id');
    }

    /**
     * Значение для того, кто не оплатил раскрытие.
     *
     * Показываем ровно столько, чтобы человек понял, что контакт реальный,
     * и не смог им воспользоваться: код оператора у телефона, первую букву
     * и домен у почты. Полностью скрывать нельзя — тогда непонятно,
     * за что платить.
     */
    public function masked(): string
    {
        return match ($this->type) {
            self::TYPE_PHONE => $this->maskPhone(),
            self::TYPE_EMAIL => $this->maskEmail(),
            self::TYPE_WEBSITE => $this->value,
            default => '••••••••',
        };
    }

    private function maskPhone(): string
    {
        $digits = preg_replace('/\D+/', '', $this->value) ?? '';

        if (mb_strlen($digits) < 7) {
            return '••• ••• •• ••';
        }

        // +998 90 ••• •• ••
        $country = mb_substr($digits, 0, mb_strlen($digits) - 9);
        $operator = mb_substr($digits, -9, 2);

        return trim(($country !== '' ? '+'.$country.' ' : '').$operator.' ••• •• ••');
    }

    private function maskEmail(): string
    {
        [$name, $domain] = array_pad(explode('@', $this->value, 2), 2, '');

        if ($domain === '') {
            return '••••••@••••.••';
        }

        return mb_substr($name, 0, 1).str_repeat('•', max(mb_strlen($name) - 1, 3)).'@'.$domain;
    }

    /** Ссылка для клика: tel:, mailto:, https://t.me/… */
    public function href(): ?string
    {
        return match ($this->type) {
            self::TYPE_PHONE => 'tel:'.preg_replace('/[^\d+]/', '', $this->value),
            self::TYPE_EMAIL => 'mailto:'.$this->value,
            self::TYPE_TELEGRAM => 'https://t.me/'.ltrim($this->value, '@'),
            self::TYPE_WHATSAPP => 'https://wa.me/'.preg_replace('/\D+/', '', $this->value),
            self::TYPE_WEBSITE => str_starts_with($this->value, 'http') ? $this->value : 'https://'.$this->value,
            default => null,
        };
    }
}
