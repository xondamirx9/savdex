<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;

/**
 * Пакет кредитов на раскрытие контактов.
 *
 * Кредиты продаются пачками, а не поштучно: покупка одного контакта
 * означала бы оплату на каждое нажатие, и человек уходил бы с кассы
 * чаще, чем с площадки.
 *
 * Цена, как у тарифов, в долларах с пересчётом по курсу ЦБ. Поле
 * в сумах перекрывает расчёт, когда витринную цену зафиксировали.
 */
#[Fillable(['code', 'name', 'credits', 'price_usd', 'price_uzs', 'sort', 'is_active'])]
class CreditPack extends Model
{
    protected function casts(): array
    {
        return ['price_usd' => 'decimal:2', 'is_active' => 'boolean'];
    }

    /** Цена в сумах: зафиксированная либо пересчитанная по курсу. */
    public function priceUzs(float $rate): int
    {
        if ($this->price_uzs !== null) {
            return $this->price_uzs;
        }

        // Округление до тысяч, как у тарифов: «131 840 сум» читается
        // как ошибка расчёта, а не как назначенная цена
        return (int) (round((float) $this->price_usd * $rate / 1000) * 1000);
    }

    /** Сколько стоит один контакт — так пакеты сравнивают между собой. */
    public function perCredit(float $rate): int
    {
        return $this->credits > 0 ? (int) round($this->priceUzs($rate) / $this->credits) : 0;
    }
}
