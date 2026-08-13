<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Транзакция платёжного провайдера по счёту.
 *
 * Отдельная строка на каждую транзакцию провайдера, а не поле на счёте:
 * протокол вроде Payme/Uzum заводит транзакцию своей стороной (create),
 * потом проводит её (perform) или отменяет (cancel) отдельными вызовами,
 * и у одного счёта их может быть несколько (отменённая попытка + удачная).
 *
 * Пара (provider, provider_transaction_id) уникальна — это и есть замок
 * идемпотентности: повторный колбэк с тем же id транзакции не создаёт
 * второй записи и не начисляет тариф дважды.
 */
#[Fillable([
    'payment_id', 'provider', 'provider_transaction_id', 'state',
    'amount_minor', 'currency', 'payload', 'performed_at', 'cancelled_at',
])]
class PaymentTransaction extends Model
{
    /** Транзакция заведена провайдером, деньги ещё не списаны. */
    public const STATE_CREATED = 'created';

    /** Деньги списаны — счёт можно закрывать и начислять. */
    public const STATE_PERFORMED = 'performed';

    /** Транзакция отменена (провайдером или возвратом). */
    public const STATE_CANCELLED = 'cancelled';

    protected function casts(): array
    {
        return [
            'payload' => 'array',
            'amount_minor' => 'integer',
            'performed_at' => 'datetime',
            'cancelled_at' => 'datetime',
        ];
    }

    public function payment(): BelongsTo
    {
        return $this->belongsTo(Payment::class);
    }
}
