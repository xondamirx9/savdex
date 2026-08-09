<?php

declare(strict_types=1);

namespace App\Support;

use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * Курс валют ЦБ Узбекистана.
 *
 * Подход InvestIn: цены задаются в долларах и пересчитываются в сумы
 * по официальному курсу. Иначе при каждом движении курса пришлось бы
 * править каждый тариф руками.
 *
 * Курс кэшируется на сутки — ЦБ публикует его раз в день. Если сервис
 * недоступен, берётся последнее известное значение: показать «цена
 * недоступна» из-за чужого сбоя хуже, чем показать вчерашнюю цену.
 */
class CurrencyRate
{
    private const URL = 'https://cbu.uz/oz/arkhiv-kursov-valyut/json/USD/';

    private const CACHE_KEY = 'cbu.rate.usd';

    private const FALLBACK_KEY = 'cbu.rate.usd.last';

    /** Запасное значение на случай, если сервис недоступен при первом же запросе. */
    private const DEFAULT = 12_800.0;

    public function usd(): float
    {
        return Cache::remember(self::CACHE_KEY, now()->addDay(), function (): float {
            try {
                $response = Http::timeout(5)->get(self::URL);

                if ($response->successful()) {
                    $rate = (float) ($response->json('0.Rate') ?? 0);

                    if ($rate > 0) {
                        // Последнее удачное значение живёт дольше суток:
                        // оно нужно именно тогда, когда основной кэш истёк,
                        // а ЦБ в этот момент недоступен
                        Cache::put(self::FALLBACK_KEY, $rate, now()->addMonth());

                        return $rate;
                    }
                }

                Log::warning('Курс ЦБ: неожиданный ответ', ['status' => $response->status()]);
            } catch (\Throwable $e) {
                Log::warning('Курс ЦБ недоступен', ['error' => $e->getMessage()]);
            }

            return (float) Cache::get(self::FALLBACK_KEY, self::DEFAULT);
        });
    }

    /** Цена в сумах, округлённая до тысяч — витрина не показывает копейки. */
    public function toUzs(float $usd): int
    {
        return (int) (round($usd * $this->usd() / 1000) * 1000);
    }
}
