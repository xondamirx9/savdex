<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Промокод на бесплатный период тарифа.
 *
 * Код одноразовый: активация проставляет used_at, и второй раз он
 * не сработает ни у кого. Кто активировал — видно в той же строке.
 *
 * Алфавит кода без похожих знаков (0/O, 1/I/L): код диктуют по телефону
 * и набирают с листовки, и «ноль или буква О» — самая частая причина
 * обращения в поддержку по промокоду.
 */
#[Fillable(['code', 'plan_id', 'days', 'expires_at', 'is_active', 'note', 'created_by'])]
class PromoCode extends Model
{
    private const ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';

    /** Длина случайной части: 8 знаков этого алфавита — 8·10¹¹ вариантов. */
    private const RANDOM_LENGTH = 8;

    protected function casts(): array
    {
        return [
            'expires_at' => 'datetime',
            'used_at' => 'datetime',
            'is_active' => 'boolean',
        ];
    }

    public function plan(): BelongsTo
    {
        return $this->belongsTo(Plan::class);
    }

    public function usedByCompany(): BelongsTo
    {
        return $this->belongsTo(Company::class, 'used_by_company_id');
    }

    public function usedByUser(): BelongsTo
    {
        return $this->belongsTo(User::class, 'used_by_user_id');
    }

    public function subscription(): BelongsTo
    {
        return $this->belongsTo(Subscription::class);
    }

    public function createdBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    /**
     * Приведение введённого кода к хранимому виду.
     *
     * Человек набирает «svdx premium-2026» — с пробелами, в нижнем
     * регистре, иногда с длинным тире вместо дефиса. Всё это один
     * и тот же код, и отказ «промокод не найден» здесь был бы обманом.
     */
    public static function normalize(string $code): string
    {
        $code = str_replace(['—', '–', '−', ' ', '_'], ['-', '-', '-', '', '-'], trim($code));

        return mb_strtoupper($code);
    }

    /** Случайный код вида SVDX-7КЗНАКОВ. */
    public static function generateCode(string $prefix = 'SVDX'): string
    {
        $random = '';

        for ($i = 0; $i < self::RANDOM_LENGTH; $i++) {
            // random_int, а не rand: угаданный код — это выданный
            // бесплатно месяц тарифа, то есть прямые потери выручки
            $random .= self::ALPHABET[random_int(0, strlen(self::ALPHABET) - 1)];
        }

        return self::normalize($prefix === '' ? $random : "{$prefix}-{$random}");
    }

    public function isUsed(): bool
    {
        return $this->used_at !== null;
    }

    public function isExpired(): bool
    {
        return $this->expires_at !== null && $this->expires_at->isPast();
    }

    /** Код, который прямо сейчас можно активировать. */
    public function isRedeemable(): bool
    {
        return $this->is_active && ! $this->isUsed() && ! $this->isExpired();
    }

    /** @param Builder<self> $query */
    public function scopeRedeemable(Builder $query): void
    {
        $query->where('is_active', true)
            ->whereNull('used_at')
            ->where(fn (Builder $q) => $q->whereNull('expires_at')->orWhere('expires_at', '>', now()));
    }
}
