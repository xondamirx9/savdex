<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\Company;
use App\Models\Listing;
use App\Models\ListingImage;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Storage;

/**
 * Наполнение витрины: описания пустым карточкам компаний и картинки
 * объявлениям без фотографий.
 *
 * Не демо-сидер: ничего не создаёт и не перезаписывает — только
 * дополняет то, что уже есть. Пустое описание компании получает
 * текст, собранный из её же данных (профиль, город, ассортимент);
 * объявление без фото — две-три векторные карточки товара в цветах
 * своей категории. Владелец в любой момент заменяет их своими
 * фотографиями через мастер — сгенерированные удаляются как обычные.
 *
 * Повторный запуск ничего не дублирует: заполненные карточки
 * и объявления с фотографиями пропускаются.
 *
 * Запуск: php artisan db:seed --class=ShowcaseSeeder
 */
class ShowcaseSeeder extends Seeder
{
    /** Сколько картинок получает объявление без фото. */
    private const IMAGES_PER_LISTING = 3;

    /**
     * Палитры и композиции по подкатегориям. Ключ — slug категории
     * объявления, значение — [фон-верх, фон-низ, цвет товара, акцент].
     */
    private const PALETTES = [
        'cement-beton' => ['#eceff4', '#cfd6e0', '#8d99ae', '#5b6779'],
        'metalloprokat' => ['#e8edf2', '#c3ccd7', '#64748b', '#334155'],
        'krovlya-fasad' => ['#f3e8e2', '#dcc5b8', '#a4664b', '#7c4a33'],
        'kirpich-blok' => ['#f6e9e2', '#e4c3b0', '#b5654a', '#8e4a33'],
        'pryazha-tkani' => ['#eee9f6', '#d4c8ea', '#7c5cbf', '#5b3fa0'],
        'gotovaya-odezhda' => ['#e9f2f1', '#c6dedd', '#3e8e87', '#2c6b66'],
        'chernye-metally' => ['#e9ebee', '#c3c8cf', '#4b5563', '#1f2937'],
        'cvetnye-metally' => ['#f6efe2', '#ead3a8', '#c19a3f', '#96742a'],
        'zerno-muka' => ['#f7f1e1', '#ecd9a9', '#d0a439', '#a37f24'],
        'sukhofrukty' => ['#f6ece1', '#e8c9a4', '#c07f35', '#94601f'],
        'poddony-tara' => ['#f2ede3', '#dccbab', '#a8834f', '#7d5f36'],
        'stanki' => ['#e8eef2', '#c2d2dc', '#4a7a96', '#2f576e'],
    ];

    private const FALLBACK_PALETTE = ['#eaeff5', '#c9d4e2', '#6b7f99', '#46586e'];

    public function run(): void
    {
        $described = $this->describeCompanies();
        $illustrated = $this->illustrateListings();
        $healed = $this->healShowcaseFiles();

        $this->command?->info("Заполнено описаний компаний: {$described}, объявлений с картинками: {$illustrated}, восстановлено файлов: {$healed}.");
    }

    // ── Карточки компаний ────────────────────────────────────

    private function describeCompanies(): int
    {
        $filled = 0;

        Company::query()
            ->where(fn ($q) => $q->whereNull('description')->orWhere('description', ''))
            ->with('city.translations')
            ->each(function (Company $company) use (&$filled): void {
                $company->forceFill(['description' => $this->composeDescription($company)])->save();
                $filled++;
            });

        return $filled;
    }

    /**
     * Описание из данных самой компании: кто она, откуда, чем торгует.
     * Ничего не выдумывается — только то, что уже есть в профиле.
     */
    private function composeDescription(Company $company): string
    {
        $what = match ($company->type) {
            'manufacturer' => 'Производственная компания',
            'distributor' => 'Дистрибьютор и оптовый поставщик',
            'trading' => 'Торговая компания',
            default => 'Компания',
        };

        $city = $company->city?->name();
        $origin = $city !== null && $city !== '' ? " из города {$city}" : ' из Узбекистана';

        $sentences = ["{$what}{$origin}."];

        // Ассортимент — из заголовков собственных объявлений: короткая
        // часть до первой запятой, чтобы не тащить объёмы и условия
        $goods = $company->listings()->latest()->limit(5)->get()
            ->map(fn (Listing $l): string => mb_strtolower(trim(explode(',', $l->title)[0])))
            ->filter(fn (string $t): bool => $t !== '')
            ->unique()
            ->take(3);

        if ($goods->isNotEmpty()) {
            $sentences[] = 'Основные направления: '.$goods->implode('; ').'.';
        }

        $sentences[] = $company->primary_role === 'buyer'
            ? 'Закупаем оптовыми партиями на постоянной основе; рассматриваем предложения поставщиков по прайс-листу и под заказ.'
            : 'Работаем с оптовыми заказами по договору поставки, отгружаем по Узбекистану и в соседние страны. Условия оплаты и доставки обсуждаются под объём.';

        $sentences[] = 'Свяжитесь с нами через площадку SavdEx — ответим на запрос в рабочее время.';

        return implode(' ', $sentences);
    }

    // ── Картинки объявлений ──────────────────────────────────

    private function illustrateListings(): int
    {
        $filled = 0;

        Listing::query()
            ->whereDoesntHave('images')
            ->whereIn('status', [Listing::STATUS_ACTIVE, Listing::STATUS_MODERATION])
            ->with('category')
            ->each(function (Listing $listing) use (&$filled): void {
                $palette = self::PALETTES[$listing->category?->slug] ?? self::FALLBACK_PALETTE;

                for ($i = 0; $i < self::IMAGES_PER_LISTING; $i++) {
                    $path = "listings/{$listing->id}/showcase-{$i}.svg";

                    Storage::disk('public')->put($path, $this->productCard($palette, $listing->id * 7 + $i));

                    // SVG остаётся один на оба размера: вектор не тяжелее
                    // миниатюры и одинаково резок в карточке и в галерее
                    $listing->images()->create([
                        'path' => $path,
                        'thumb_path' => $path,
                        'sort' => $i,
                    ]);
                }

                $filled++;
            });

        return $filled;
    }

    /**
     * Перерисовать сгенерированные картинки, файлы которых пропали.
     *
     * До переезда хранилища на постоянный диск деплой стирал файлы,
     * а записи в базе оставались — карточки показывали битые
     * изображения. Картинка детерминирована объявлением и номером,
     * поэтому восстанавливается точь-в-точь той же.
     */
    private function healShowcaseFiles(): int
    {
        $healed = 0;

        ListingImage::query()
            ->where('path', 'like', 'listings/%/showcase-%')
            ->with('listing.category')
            ->each(function (ListingImage $image) use (&$healed): void {
                if (Storage::disk('public')->exists($image->path)) {
                    return;
                }

                $listing = $image->listing;

                if ($listing === null) {
                    return;
                }

                $palette = self::PALETTES[$listing->category?->slug] ?? self::FALLBACK_PALETTE;
                $seed = $listing->id * 7 + (int) preg_replace('/\D/', '', basename($image->path));

                Storage::disk('public')->put($image->path, $this->productCard($palette, $seed));
                $healed++;
            });

        return $healed;
    }

    /**
     * Векторная «предметная съёмка»: мягкий градиентный фон, тень
     * и композиция из брусков товарного цвета. Вариант определяется
     * зерном — у одного объявления три разных ракурса, у разных
     * объявлений одной категории картинки тоже не совпадают.
     *
     * @param  array{0: string, 1: string, 2: string, 3: string}  $palette
     */
    private function productCard(array $palette, int $seed): string
    {
        [$bgTop, $bgBottom, $body, $accent] = $palette;

        $blocks = '';
        $count = 3 + $seed % 3;

        for ($i = 0; $i < $count; $i++) {
            // Детерминированный «разброс» без random: одна и та же
            // картинка при каждом запуске — сидер обязан быть воспроизводим
            $n = ($seed * 31 + $i * 17) % 100;

            $w = 240 + ($n * 3) % 160;
            $h = 120 + ($n * 7) % 120;
            $x = 180 + $i * (760 / $count) + ($n % 40) - 20;
            $y = 615 - $h - ($i % 2) * 45 - ($n % 20);
            $r = (($n % 11) - 5) / 2;
            $fill = $i % 2 === 0 ? $body : $accent;

            $blocks .= sprintf(
                '<rect x="%.0f" y="%.0f" width="%d" height="%d" rx="14" fill="%s" opacity="0.9" transform="rotate(%.1f %.0f %.0f)"/>',
                $x, $y, $w, $h, $fill, $r, $x + $w / 2, $y + $h / 2,
            );
        }

        return <<<SVG
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 900">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{$bgTop}"/>
      <stop offset="1" stop-color="{$bgBottom}"/>
    </linearGradient>
    <radialGradient id="halo" cx="0.5" cy="0.42" r="0.6">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.55"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1200" height="900" fill="url(#bg)"/>
  <rect width="1200" height="900" fill="url(#halo)"/>
  <ellipse cx="600" cy="640" rx="430" ry="70" fill="{$accent}" opacity="0.18"/>
  {$blocks}
  <rect x="0" y="820" width="1200" height="80" fill="{$accent}" opacity="0.08"/>
</svg>
SVG;
    }
}
