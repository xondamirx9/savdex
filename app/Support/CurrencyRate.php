<?php

declare(strict_types=1);

namespace App\Support;

use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * Курсы валют ЦБ Узбекистана.
 *
 * Подход InvestIn: тарифы задаются в долларах и пересчитываются в сумы
 * по официальному курсу. Иначе при каждом движении курса пришлось бы
 * править каждый тариф руками. Витрина тем же курсом переводит цену
 * продавца в валюту языка: на английской версии — в доллары,
 * на китайской — в юани (PriceDisplay).
 *
 * Таблица берётся целиком, а не по валюте: одна выгрузка в сутки
 * вместо запроса на каждую валюту, и все курсы одной даты. ЦБ
 * публикует их раз в день — столько таблица и живёт в кэше. Если
 * сервис недоступен, берётся последняя известная: показать «цена
 * недоступна» из-за чужого сбоя хуже, чем показать вчерашнюю цену.
 */
class CurrencyRate
{
    private const URL = 'https://cbu.uz/oz/arkhiv-kursov-valyut/json/';

    private const CACHE_KEY = 'cbu.rates';

    private const FALLBACK_KEY = 'cbu.rates.last';

    /** Ключ последнего курса доллара до того, как таблица стала общей. */
    private const LEGACY_USD_KEY = 'cbu.rate.usd.last';

    /**
     * Запасной курс доллара на случай, если сервис недоступен при первом
     * же запросе. Только для кассы: тарифы заданы в долларах, и без
     * курса она встала бы. Витрина (rate) запасным курсом не пользуется:
     * без курса она показывает цену продавца как есть — придуманный
     * курс показал бы покупателю неправду.
     */
    private const DEFAULT_USD = 12_800.0;

    /**
     * Таблица на время запроса: кэш — поход в Redis, а карточек
     * на странице десятки.
     *
     * @var array<string, float>|null
     */
    private ?array $table = null;

    /** Курс доллара для кассы — известен всегда. */
    public function usd(): float
    {
        return $this->rate('USD') ?? self::DEFAULT_USD;
    }

    /** Сколько сумов стоит единица валюты; null — курса нет. Сум — единица. */
    public function rate(string $code): ?float
    {
        if ($code === 'UZS') {
            return 1.0;
        }

        return $this->rates()[$code] ?? null;
    }

    /** Перевод суммы между валютами через сум; null — курса одной из них нет. */
    public function convert(float $amount, string $from, string $to): ?float
    {
        if ($from === $to) {
            return $amount;
        }

        $fromRate = $this->rate($from);
        $toRate = $this->rate($to);

        if ($fromRate === null || $toRate === null) {
            return null;
        }

        return $amount * $fromRate / $toRate;
    }

    /** Цена в сумах, округлённая до тысяч — витрина не показывает копейки. */
    public function toUzs(float $usd): int
    {
        return (int) (round($usd * $this->usd() / 1000) * 1000);
    }

    /**
     * Обновление таблицы по расписанию, не дожидаясь запроса.
     *
     * Без этого таблицу подтягивал бы первый посетитель после того,
     * как кэш истёк, — и ждал бы ответа ЦБ до пяти секунд на главной.
     * Неудачная попытка ничего не трогает: в кэше остаётся прежняя
     * таблица, за неё отвечает load().
     */
    public function refresh(): bool
    {
        $fresh = $this->fetch();

        if ($fresh === null) {
            return false;
        }

        Cache::put(self::CACHE_KEY, $fresh, now()->addDay());
        Cache::put(self::FALLBACK_KEY, $fresh, now()->addMonth());
        $this->table = $fresh;

        return true;
    }

    /**
     * Таблица «код → сумов за единицу».
     *
     * Неудачная выгрузка кэшируется только на час, а не на сутки:
     * иначе сбой ЦБ в минуту первого запроса оставил бы витрину
     * без курсов до завтра.
     *
     * @return array<string, float>
     */
    private function rates(): array
    {
        return $this->table ??= $this->load();
    }

    /** @return array<string, float> */
    private function load(): array
    {
        $cached = Cache::get(self::CACHE_KEY);

        if (is_array($cached)) {
            return $cached;
        }

        $fresh = $this->fetch();

        if ($fresh !== null) {
            Cache::put(self::CACHE_KEY, $fresh, now()->addDay());
            // Последняя удачная таблица живёт дольше суток: она нужна
            // именно тогда, когда основной кэш истёк, а ЦБ недоступен
            Cache::put(self::FALLBACK_KEY, $fresh, now()->addMonth());

            return $fresh;
        }

        $last = Cache::get(self::FALLBACK_KEY);
        $last = is_array($last) ? $last : [];

        // Курс доллара, запомненный до общей таблицы: в первые дни
        // после выкладки он ещё лежит под старым ключом, и вчерашний
        // настоящий курс лучше запасной константы
        $legacy = (float) Cache::get(self::LEGACY_USD_KEY, 0);

        if ($last === [] && $legacy > 0) {
            $last = ['USD' => $legacy];
        }

        Cache::put(self::CACHE_KEY, $last, now()->addHour());

        return $last;
    }

    /** @return array<string, float>|null */
    private function fetch(): ?array
    {
        try {
            $response = Http::timeout(5)->get(self::URL);

            if ($response->successful()) {
                $rates = [];

                foreach ((array) $response->json() as $row) {
                    if (! is_array($row)) {
                        continue;
                    }

                    $code = strtoupper(trim((string) ($row['Ccy'] ?? '')));
                    // Курс некоторых валют ЦБ даёт за 10 или 100 единиц
                    $nominal = (float) ($row['Nominal'] ?? 1) ?: 1.0;
                    $rate = (float) ($row['Rate'] ?? 0) / $nominal;

                    if ($code !== '' && $rate > 0) {
                        $rates[$code] = $rate;
                    }
                }

                if ($rates !== []) {
                    return $rates;
                }
            }

            Log::warning('Курс ЦБ: неожиданный ответ', ['status' => $response->status()]);
        } catch (\Throwable $e) {
            Log::warning('Курс ЦБ недоступен', ['error' => $e->getMessage()]);
        }

        return null;
    }
}
