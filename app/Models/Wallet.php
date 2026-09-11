<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Facades\DB;
use InvalidArgumentException;

/**
 * Кошелёк компании: кредиты на контакты и единицы продвижения.
 *
 * Кошелёк один на компанию, а не на сотрудника: лимиты тарифа считаются
 * на компанию, кредиты — общий счёт (§3 ТЗ).
 */
#[Fillable(['company_id', 'credits', 'promo_units', 'contacts_used_this_period', 'responses_used_this_period', 'period_resets_at'])]
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
     * Счета кошелька. Имя счёта подставляется в SQL как имя колонки,
     * поэтому список закрытый, а не любая строка от вызывающего.
     *
     * @var list<string>
     */
    private const KINDS = ['credits', 'promo_units', 'contacts_used_this_period', 'responses_used_this_period'];

    /**
     * Списание с записью в историю.
     *
     * Проверка остатка — условием самого UPDATE, а не отдельным чтением:
     * «прочитать баланс, сравнить, записать» между чтением и записью
     * пропускает второго, и два одновременных раскрытия контакта
     * списывали один кредит дважды. Здесь выигрывает ровно один запрос,
     * второму база возвращает ноль изменённых строк.
     *
     * lockForUpdate для этого не годился: на SQLite он не блокирует
     * ничего (см. PromoCodeService::capture), а условный UPDATE
     * одинаково верен на обеих СУБД.
     *
     * @return bool false, если средств не хватает
     */
    public function spend(string $kind, int $amount, string $reason, ?Model $subject = null, ?int $userId = null): bool
    {
        $this->assertKind($kind);

        return DB::transaction(function () use ($kind, $amount, $reason, $subject, $userId): bool {
            $affected = self::query()
                ->whereKey($this->id)
                ->where($kind, '>=', $amount)
                ->decrement($kind, $amount);

            if ($affected === 0) {
                return false;
            }

            // Строку держит наша же транзакция: перечитанное значение —
            // результат именно нашего списания, чужое сюда не попадёт
            $this->syncFromStorage($kind, -$amount, $reason, $subject, $userId);

            return true;
        });
    }

    public function grant(string $kind, int $amount, string $reason, ?Model $subject = null, ?int $userId = null): void
    {
        $this->assertKind($kind);

        DB::transaction(function () use ($kind, $amount, $reason, $subject, $userId): void {
            self::query()->whereKey($this->id)->increment($kind, $amount);

            $this->syncFromStorage($kind, $amount, $reason, $subject, $userId);
        });
    }

    /** Запись в историю по фактическому остатку и обновление модели. */
    private function syncFromStorage(string $kind, int $amount, string $reason, ?Model $subject, ?int $userId): void
    {
        $fresh = self::query()->findOrFail($this->id);

        $this->record($kind, $amount, (int) $fresh->{$kind}, $reason, $subject, $userId);
        $this->fill($fresh->only(self::KINDS));
    }

    private function assertKind(string $kind): void
    {
        if (! in_array($kind, self::KINDS, true)) {
            throw new InvalidArgumentException("Неизвестный счёт кошелька: {$kind}");
        }
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
