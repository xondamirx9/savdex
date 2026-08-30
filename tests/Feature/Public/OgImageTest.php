<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Listing;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Storage;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * og:image для мессенджеров: только растр.
 *
 * Превью-боты Telegram и WhatsApp не понимают SVG — ссылка на
 * объявление с векторной картинкой расходилась голым текстом
 * (аудит 29.08.2026, п. 6.1). Маршрут /og/listing/{id}.jpg отдаёт
 * JPEG 1200×630 из первого растрового фото либо фирменную обложку.
 */
class OgImageTest extends TestCase
{
    use RefreshDatabase;

    private function listing(): Listing
    {
        return Listing::factory()->create([
            'company_id' => Company::factory()->create(['status' => 'active'])->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'expires_at' => now()->addDays(30),
        ]);
    }

    /** Настоящее фото в webp, как его сохраняет ImageStore. */
    private function webp(int $w = 1600, int $h = 900): string
    {
        $im = imagecreatetruecolor($w, $h);
        imagefill($im, 0, 0, (int) imagecolorallocate($im, 40, 90, 160));
        ob_start();
        imagewebp($im, null, 80);

        return (string) ob_get_clean();
    }

    #[Test]
    public function превью_собирается_в_jpeg_1200_на_630(): void
    {
        Storage::fake('public');

        $listing = $this->listing();
        Storage::disk('public')->put("listings/{$listing->id}/photo.webp", $this->webp());
        $image = $listing->images()->create([
            'path' => "listings/{$listing->id}/photo.webp",
            'thumb_path' => "listings/{$listing->id}/photo.webp",
            'sort' => 0,
        ]);

        $this->get("/og/listing/{$listing->id}.jpg")
            ->assertRedirect(asset("storage/listings/{$listing->id}/og-{$image->id}.jpg"));

        $jpeg = Storage::disk('public')->get("listings/{$listing->id}/og-{$image->id}.jpg");
        $size = getimagesizefromstring($jpeg);

        $this->assertSame(1200, $size[0]);
        $this->assertSame(630, $size[1]);
        $this->assertSame('image/jpeg', $size['mime']);
    }

    /** SVG-заглушки в превью не годятся — отдаётся фирменная обложка. */
    #[Test]
    public function без_растрового_фото_отдаётся_фирменная_обложка(): void
    {
        Storage::fake('public');

        $listing = $this->listing();
        Storage::disk('public')->put("listings/{$listing->id}/showcase-0.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>');
        $listing->images()->create([
            'path' => "listings/{$listing->id}/showcase-0.svg",
            'thumb_path' => "listings/{$listing->id}/showcase-0.svg",
            'sort' => 0,
        ]);

        $this->get("/og/listing/{$listing->id}.jpg")->assertRedirect(asset('og-cover.png'));
    }

    #[Test]
    public function карточка_объявления_указывает_растровое_превью(): void
    {
        $listing = $this->listing();
        $listing->forceFill(['slug' => Listing::makeSlug($listing->title, $listing->id)])->save();

        $this->get("/listing/{$listing->slug}")
            ->assertSee('/og/listing/'.$listing->id.'.jpg', false)
            ->assertSee('og:image:width', false);
    }
}
