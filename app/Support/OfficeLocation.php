<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Setting;

/**
 * Адрес офиса и точка на карте для страницы «О компании».
 *
 * Всё берётся из настроек площадки, а не из вёрстки: переезд офиса
 * — это правка одной строки в админке, а не деплой.
 *
 * Координаты хранятся одной строкой «41.311081, 69.240562», а не
 * двумя числовыми настройками. Именно в таком виде их отдаёт кнопка
 * «скопировать координаты» в Яндекс.Картах и Google Maps: администратор
 * находит дом на карте, копирует и вставляет. Два поля вынуждали бы
 * разрезать строку руками — а перепутанные местами широта и долгота
 * уводят метку в океан, и по карте это не всегда заметно.
 */
class OfficeLocation
{
    public const KEY_ADDRESS = 'office_address';

    public const KEY_COORDS = 'office_coords';

    public const KEY_ZOOM = 'office_map_zoom';

    /**
     * Строка координат, которую принимает разбор.
     *
     * Широта до 90, долгота до 180 — иначе метка оказывается за краем
     * карты. Разделитель — запятая, вокруг неё пробелы необязательны.
     */
    public const COORDS_PATTERN = '/^\s*-?\d{1,2}(\.\d+)?\s*,\s*-?\d{1,3}(\.\d+)?\s*$/';

    /** Дом целиком и соседние кварталы вокруг — по такой карте офис находят. */
    private const DEFAULT_ZOOM = 16;

    /** Ниже 3 карта показывает полушарие, выше 19 у OpenStreetMap нет тайлов. */
    private const MIN_ZOOM = 3;

    private const MAX_ZOOM = 19;

    /**
     * Данные офиса для витрины или null, если в настройках пусто.
     *
     * Пустые настройки — обычное состояние свежей установки, и раздел
     * «Офис» в этом случае не показывается вовсе. Заголовок с прочерком
     * вместо адреса выглядит как поломка, а не как «адрес не указан».
     *
     * @return array{address: string, lat: float|null, lng: float|null, zoom: int, hours: string}|null
     */
    public static function current(): ?array
    {
        $address = trim((string) Setting::get(self::KEY_ADDRESS, ''));
        [$lat, $lng] = self::coords((string) Setting::get(self::KEY_COORDS, ''));

        // Карта без адреса и адрес без карты — оба варианта рабочие:
        // офис бывает в здании, которое на карте есть, а в адресном
        // справочнике ещё нет, и наоборот.
        if ($address === '' && $lat === null) {
            return null;
        }

        return [
            'address' => $address,
            'lat' => $lat,
            'lng' => $lng,
            'zoom' => self::zoom(),
            'hours' => trim((string) Setting::get('support_hours', '')),
        ];
    }

    /**
     * Разбор строки «41.311081, 69.240562» в пару чисел.
     *
     * Неразобранная строка даёт пару null, а не исключение: настройку
     * правят в админке, и опечатка в ней не должна ронять публичную
     * страницу — карта просто не показывается.
     *
     * @return array{0: float|null, 1: float|null}
     */
    public static function coords(string $raw): array
    {
        if (preg_match(self::COORDS_PATTERN, $raw) !== 1) {
            return [null, null];
        }

        [$lat, $lng] = array_map(
            static fn (string $part): float => (float) trim($part),
            explode(',', $raw, 2),
        );

        // Регулярное выражение ограничивает только число знаков:
        // «95.0, 200.0» ему подходит, а такой точки на глобусе нет.
        if (abs($lat) > 90 || abs($lng) > 180) {
            return [null, null];
        }

        return [$lat, $lng];
    }

    /** Масштаб карты из настроек, зажатый в границы, которые умеет OpenStreetMap. */
    private static function zoom(): int
    {
        $zoom = (int) Setting::get(self::KEY_ZOOM, self::DEFAULT_ZOOM);

        if ($zoom === 0) {
            return self::DEFAULT_ZOOM;
        }

        return max(self::MIN_ZOOM, min(self::MAX_ZOOM, $zoom));
    }
}
