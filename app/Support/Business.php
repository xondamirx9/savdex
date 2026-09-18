<?php

declare(strict_types=1);

namespace App\Support;

use Illuminate\Support\Carbon;

/**
 * Часовой пояс, в котором площадка ведёт свои дела.
 *
 * Приложение работает в UTC — так хранятся все отметки времени, и
 * менять это нельзя: записи, сделанные до смены, остались бы в UTC,
 * а новые пошли бы в местном времени, и отличить одни от других было
 * бы нечем.
 *
 * Но деньги считают по местному календарю. Ташкент — UTC+5, и оплата
 * в два часа ночи первого октября в UTC приходится на тридцатое
 * сентября. В месячном отчёте она попадала в сентябрь, хотя для
 * бухгалтерии это октябрь. Раз в месяц пять часов выручки уезжали
 * в соседний период — не потеря, но расхождение с тем, что человек
 * считает месяцем.
 *
 * Поэтому границы периодов и разбивка по месяцам считаются здесь,
 * а хранение остаётся в UTC.
 *
 * Если бухгалтерия площадки перейдёт на другой пояс, меняется одно
 * значение: BUSINESS_TIMEZONE в окружении (config/app.php).
 */
final class Business
{
    public const DEFAULT_TIMEZONE = 'Asia/Tashkent';

    /**
     * Через config(), а не env(): на боевой площадке конфигурация
     * кэшируется при запуске контейнера, и env() после этого
     * возвращает null. Отчёт молча уехал бы обратно в UTC.
     */
    public static function timezone(): string
    {
        $value = config('app.business_timezone', self::DEFAULT_TIMEZONE);

        return is_string($value) && $value !== '' ? $value : self::DEFAULT_TIMEZONE;
    }

    /**
     * Начало местного дня, в UTC — для запроса к базе.
     *
     * Принимается календарная дата «Y-m-d», а не момент времени:
     * момент пришлось бы сперва перевести в местный пояс, и «конец
     * сентября по UTC» превратился бы в первое октября по Ташкенту.
     * Двусмысленность убрана из подписи метода, а не оставлена
     * на внимательность вызывающего.
     */
    public static function startOfDay(string $day): Carbon
    {
        return Carbon::parse($day, self::timezone())->startOfDay()->utc();
    }

    /** Конец местного дня, в UTC. */
    public static function endOfDay(string $day): Carbon
    {
        return Carbon::parse($day, self::timezone())->endOfDay()->utc();
    }

    /** Сегодняшняя дата по местному календарю. */
    public static function today(): Carbon
    {
        return Carbon::now(self::timezone())->startOfDay();
    }

    /**
     * Границы текущего местного месяца, в UTC.
     *
     * Умолчание для финансовых экранов: «этот месяц» — тот, который
     * человек видит в календаре у себя, а не в UTC.
     *
     * @return array{0: string, 1: string} даты «Y-m-d»
     */
    public static function currentMonth(): array
    {
        $today = self::today();

        return [
            $today->copy()->startOfMonth()->toDateString(),
            $today->copy()->endOfMonth()->toDateString(),
        ];
    }

    /** Отметка времени из базы — в местном календаре, для группировки и показа. */
    public static function local(Carbon $moment): Carbon
    {
        return $moment->copy()->setTimezone(self::timezone());
    }
}
