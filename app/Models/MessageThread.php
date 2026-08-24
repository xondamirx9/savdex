<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Carbon;

/**
 * Разговор двух компаний вокруг объявления.
 *
 * Покупатель — кто откликнулся, продавец — владелец объявления.
 * Роли фиксируются при создании и не меняются: по ним считается
 * непрочитанное и определяется собеседник.
 */
#[Fillable(['listing_id', 'buyer_company_id', 'seller_company_id', 'last_message_at'])]
class MessageThread extends Model
{
    protected function casts(): array
    {
        return [
            'buyer_read_at' => 'datetime',
            'seller_read_at' => 'datetime',
            'last_message_at' => 'datetime',
        ];
    }

    public function listing(): BelongsTo
    {
        return $this->belongsTo(Listing::class);
    }

    public function buyer(): BelongsTo
    {
        return $this->belongsTo(Company::class, 'buyer_company_id');
    }

    public function seller(): BelongsTo
    {
        return $this->belongsTo(Company::class, 'seller_company_id');
    }

    public function messages(): HasMany
    {
        return $this->hasMany(Message::class, 'thread_id');
    }

    public function isParticipant(Company $company): bool
    {
        return $this->buyer_company_id === $company->id || $this->seller_company_id === $company->id;
    }

    /** Собеседник для стороны $company. */
    public function counterpart(Company $company): ?Company
    {
        return $this->buyer_company_id === $company->id ? $this->seller : $this->buyer;
    }

    /** Отметка «до какого момента прочитано» для стороны $company. */
    public function readAtFor(Company $company): ?Carbon
    {
        return $this->buyer_company_id === $company->id ? $this->buyer_read_at : $this->seller_read_at;
    }

    /** Непрочитанные стороной $company сообщения собеседника. */
    public function unreadCountFor(Company $company): int
    {
        $readAt = $this->readAtFor($company);

        return $this->messages()
            ->where('company_id', '!=', $company->id)
            ->when($readAt !== null, fn (Builder $q) => $q->where('created_at', '>', $readAt))
            ->count();
    }

    public function markReadFor(Company $company): void
    {
        $column = $this->buyer_company_id === $company->id ? 'buyer_read_at' : 'seller_read_at';

        $this->forceFill([$column => now()])->save();
    }

    /**
     * Сколько разговоров компании держат непрочитанное — цифра
     * у пункта «Чаты» в кабинете. COALESCE вместо whereColumn:
     * непрочитанный тред с пустой отметкой чтения иначе выпадал бы
     * из сравнения с NULL.
     */
    public static function unreadThreadsFor(Company $company): int
    {
        $hasUnread = fn (string $readColumn) => fn ($q) => $q
            ->selectRaw('1')
            ->from('messages')
            ->whereColumn('messages.thread_id', 'message_threads.id')
            ->where('messages.company_id', '!=', $company->id)
            ->whereRaw("messages.created_at > COALESCE(message_threads.{$readColumn}, '1970-01-01 00:00:00')");

        return self::query()
            ->where(fn (Builder $q) => $q
                ->where(fn (Builder $b) => $b
                    ->where('buyer_company_id', $company->id)
                    ->whereExists($hasUnread('buyer_read_at')))
                ->orWhere(fn (Builder $b) => $b
                    ->where('seller_company_id', $company->id)
                    ->whereExists($hasUnread('seller_read_at'))))
            ->count();
    }

    /** @param Builder<self> $query */
    public function scopeParticipant(Builder $query, Company $company): void
    {
        $query->where(fn (Builder $q) => $q
            ->where('buyer_company_id', $company->id)
            ->orWhere('seller_company_id', $company->id));
    }
}
