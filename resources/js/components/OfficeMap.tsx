import { Clock, MapPin, Navigation } from 'lucide-react';

/**
 * Офис площадки: адрес, часы работы и точка на карте.
 *
 * Данные приходят с сервера из настроек площадки — адрес и координаты
 * меняются в админке, без правки вёрстки.
 */
export type Office = {
    address: string;
    lat: number | null;
    lng: number | null;
    zoom: number;
    hours: string;
};

/**
 * Карта — врезка OpenStreetMap.
 *
 * У Яндекса и Google встраивание требует ключа API: ключ нужно завести,
 * привязать к домену, следить за квотой, а на превышении карта гаснет.
 * Врезка OSM не требует ни ключа, ни стороннего скрипта на странице —
 * это обычный iframe, который грузится сам и только при прокрутке до
 * него. Кнопки ниже уводят в Яндекс.Карты и Google Maps, где строится
 * маршрут: именно за маршрутом человек уходит с карточки офиса.
 */
function embedSrc(lat: number, lng: number, zoom: number): string {
    /*
     * Врезка принимает не масштаб, а прямоугольник в градусах.
     * Ширина одного тайла — 360 / 2^zoom градусов; во врезку по
     * ширине помещается примерно три тайла.
     */
    const lngSpan = (360 / 2 ** zoom) * 3;

    /*
     * По вертикали градус занимает больше пикселей, чем по
     * горизонтали, — в cos(широты) раз (проекция Меркатора).
     * Множитель 0.45 — отношение высоты врезки к её ширине:
     * без него прямоугольник вытягивается, и OSM показывает
     * район вместо дома.
     */
    const latSpan = lngSpan * Math.cos((lat * Math.PI) / 180) * 0.45;

    const bbox = [lng - lngSpan / 2, lat - latSpan / 2, lng + lngSpan / 2, lat + latSpan / 2];

    return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox.join('%2C')}&layer=mapnik&marker=${lat}%2C${lng}`;
}

/** Ссылки во внешние карты: там строится маршрут и работает поиск проезда. */
function externalLinks(lat: number, lng: number, zoom: number): [string, string][] {
    return [
        // У Яндекса координаты идут в обратном порядке — долгота, широта
        ['Яндекс.Карты', `https://yandex.uz/maps/?ll=${lng}%2C${lat}&z=${zoom}&pt=${lng}%2C${lat}`],
        ['Google Maps', `https://www.google.com/maps/search/?api=1&query=${lat}%2C${lng}`],
    ];
}

export function OfficeMap({ office }: { office: Office }) {
    const { address, lat, lng, zoom, hours } = office;
    // Координаты необязательны: адрес без метки на карте — рабочий
    // случай, здание может ещё не быть в справочнике
    const hasPoint = lat !== null && lng !== null;

    return (
        <>
            <div className="grid grid-2">
                <div className="card row" style={{ gap: 16, alignItems: 'flex-start' }}>
                    <span className="ico-box ico-box-lg">
                        <MapPin aria-hidden className="size-5" />
                    </span>
                    <div style={{ minWidth: 0 }}>
                        <h3 className="t-h4" style={{ marginBottom: 4 }}>
                            Адрес
                        </h3>
                        <p className="t-body" style={{ overflowWrap: 'anywhere' }}>
                            {address || 'Уточняется'}
                        </p>
                    </div>
                </div>

                {hours !== '' && (
                    <div className="card row" style={{ gap: 16, alignItems: 'flex-start' }}>
                        <span className="ico-box ico-box-lg">
                            <Clock aria-hidden className="size-5" />
                        </span>
                        <div style={{ minWidth: 0 }}>
                            <h3 className="t-h4" style={{ marginBottom: 4 }}>
                                Часы работы
                            </h3>
                            <p className="t-body">{hours}</p>
                        </div>
                    </div>
                )}
            </div>

            {hasPoint && (
                <>
                    <div className="map-frame mt-24">
                        <iframe
                            // Карта грузится, только когда до неё доскроллили:
                            // на странице она пятым разделом, и большинство
                            // читателей до неё не доходит вовсе
                            loading="lazy"
                            src={embedSrc(lat, lng, zoom)}
                            title={address !== '' ? `Офис на карте: ${address}` : 'Офис на карте'}
                        />
                    </div>

                    <div className="row mt-16" style={{ gap: 10, flexWrap: 'wrap' }}>
                        {externalLinks(lat, lng, zoom).map(([label, href]) => (
                            <a
                                key={label}
                                href={href}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn btn-secondary btn-sm"
                            >
                                <Navigation aria-hidden className="size-4" />
                                {label}
                            </a>
                        ))}
                    </div>
                </>
            )}
        </>
    );
}
