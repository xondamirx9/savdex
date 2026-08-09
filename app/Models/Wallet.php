<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Facades\DB;

/**
 * Кошелёк компании: кредиты на контакты и единицы продвижения.
 *
 * Кошелёк один на компанию, а не на сотрудника: лимиты тарифа считаются
 * на компанию, кредиты — общий счёт (§3 ТЗ).
 */
#[Fillable(['company_id', 'credits', 'promo_units', 'contacts_used_this_period', 'period_resets_at'])]
class Wallet extends Model
{
    protected function casts(): array
    {
        return ['period_resets_at' => 'datetime'];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    /**
     * Списание с записью в историю.
     *
     * Всё внутри транзакции с блокировкой строки: два одновременных
     * раскрытия контакта с одного аккаунта иначе спишут один кредит
     * дважды и уведут баланс в минус.
     *
     * @return bool false, если средств не хватает
     */
    public function spend(string $kind, int $amount, string $reason, ?Model $subject = null, ?int $userId = null): bool
    {
        return DB::transaction(function () use ($kind, $amount, $reason, $subject, $userId): bool {
            $fresh = self::query()->lockForUpdate()->find($this->id);

            if ($fresh === null || $fresh->{$kind} < $amount) {
                return false;
            }

            $fresh->decrement($kind, $amount);
            $fresh->refresh();

            $this->record($kind, -$amount, $fresh->{$kind}, $reason, $subject, $userId);
            $this->fill($fresh->only(['credits', 'promo_units', 'contacts_used_this_period']));

            return true;
        });
    }

    public function grant(string $kind, int $amount, string $reason, ?Model $subject = null, ?int $userId = null): void
    {
        DB::transaction(function () use ($kind, $amount, $reason, $subject, $userId): void {
            $fresh = self::query()->lockForUpdate()->find($this->id);
            $fresh->increment($kind, $amount);
            $fresh->refresh();

            $this->record($kind, $amount, $fresh->{$kind}, $reason, $subject, $userId);
            $this->fill($fresh->only(['credits', 'promo_units', 'contacts_used_this_period']));
        });
    }

    private function record(string $kind, int $amount, int $balanceAfter, string $reason, ?Model $subject, ?int $userId): void
    {
        WalletTransaction::create([
            'company_id' => $this->company_id,
            'user_id' => $userId,
            'kind' => $kind,
            'amount' => $amount,
            'balance_after' => $balanceAfter,
            'reason' => $reason,
            'subject_type' => $subject?->getMorphClass(),
            'subject_id' => $subject?->getKey(),
        ]);
    }
}
