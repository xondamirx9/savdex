<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Listing;
use Illuminate\Http\RedirectResponse;
use Illuminate\Support\Facades\Storage;

/**
 * Растровое превью объявления для og:image.
 *
 * Превью-боты Telegram, WhatsApp и Facebook не понимают SVG — ссылка
 * на объявление с векторной заглушкой расходилась без картинки вовсе
 * (аудит 29.08.2026, п. 6.1). Здесь первое растровое фото объявления
 * пережимается в JPEG 1200×630 (кроп по центру) и кэшируется на диске;
 * без растрового фото отдаётся фирменная обложка.
 *
 * Имя кэша включает id исходного фото: сменилась обложка объявления —
 * старый файл просто перестаёт запрашиваться.
 */
class OgImageController extends Controller
{
    private const WIDTH = 1200;

    private const HEIGHT = 630;

    public function __invoke(int $id): RedirectResponse
    {
        $listing = Listing::query()->with('images')->findOrFail($id);

        $source = $listing->images
            ->sortBy('sort')
            ->first(fn ($image): bool => ! str_ends_with(mb_strtolower((string) $image->path), '.svg')
                && Storage::disk('public')->exists($image->path));

        if ($source === null) {
            return redirect(asset('og-cover.png'));
        }

        $cached = "listings/{$listing->id}/og-{$source->id}.jpg";

        if (! Storage::disk('public')->exists($cached) && ! $this->render((string) $source->path, $cached)) {
            return redirect(asset('og-cover.png'));
        }

        return redirect(asset('storage/'.$cached));
    }

    /** Пережать фото в JPEG 1200×630 с кропом по центру. */
    private function render(string $sourcePath, string $targetPath): bool
    {
        $binary = Storage::disk('public')->get($sourcePath);
        $image = $binary === null ? false : @imagecreatefromstring($binary);

        if ($image === false) {
            return false;
        }

        $width = imagesx($image);
        $height = imagesy($image);

        // cover: заполнить рамку целиком, лишнее обрезать по центру
        $scale = max(self::WIDTH / $width, self::HEIGHT / $height);
        $cropWidth = (int) round(self::WIDTH / $scale);
        $cropHeight = (int) round(self::HEIGHT / $scale);

        $target = imagecreatetruecolor(self::WIDTH, self::HEIGHT);

        // JPEG прозрачность не хранит — прозрачные PNG кладутся на белый
        imagefill($target, 0, 0, (int) imagecolorallocate($target, 255, 255, 255));

        imagecopyresampled(
            $target, $image,
            0, 0,
            (int) (($width - $cropWidth) / 2), (int) (($height - $cropHeight) / 2),
            self::WIDTH, self::HEIGHT,
            $cropWidth, $cropHeight,
        );

        ob_start();
        imagejpeg($target, null, 84);
        $jpeg = (string) ob_get_clean();

        imagedestroy($image);
        imagedestroy($target);

        return Storage::disk('public')->put($targetPath, $jpeg) !== false;
    }
}
