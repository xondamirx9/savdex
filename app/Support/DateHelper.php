<?php

declare(strict_types=1);

namespace App\Support;

use Illuminate\Support\Carbon;

class DateHelper
{
    /**
     * Месяцы в родительном падеже.
     *
     * Carbon отдаёт именительный: translatedFormat('F Y') даёт «июль 2026»,
     * и получается «на площадке с июль 2026». Родительный падеж Carbon
     * подставляет только вместе с числом («28 июля»), а число здесь лишнее.
     */
    private const MONTHS_GENITIVE = [
        1 => 'января', 2 => 'февраля', 3 => 'марта', 4 => 'апреля',
        5 => 'мая', 6 => 'июня', 7 => 'июля', 8 => 'августа',
        9 => 'сентября', 10 => 'октября', 11 => 'ноября', 12 => 'декабря',
    ];

    /** «июля 2026» — для конструкций вида «на площадке с …». */
    public static function monthYear(?Carbon $date): ?string
    {
        if ($date === null) {
            return null;
        }

        if (app()->getLocale() !== 'ru') {
            return $date->isoFormat('MMMM YYYY');
        }

        return self::MONTHS_GENITIVE[$date->month].' '.$date->year;
    }

    /** «24 июля 2026» — дата публикации новости. */
    public static function dayMonthYear(?Carbon $date): ?string
    {
        if ($date === null) {
            return null;
        }

        if (app()->getLocale() !== 'ru') {
            return $date->isoFormat('D MMMM YYYY');
        }

        return $date->day.' '.self::MONTHS_GENITIVE[$date->month].' '.$date->year;
    }
}
