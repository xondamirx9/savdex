<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Загрузка изображений: логотип компании и фотографии объявлений.
 *
 * Мастер объявлений обещал, что карточки с фото открывают заметно
 * чаще, и предлагал вместо загрузки надпись «появится позже».
 *
 * Файл пересобирается, а не сохраняется как есть: снимок с камеры
 * весит мегабайты, а в его метаданных может лежать что угодно.
 * Наружу выходит только то, что GD прочитал как пиксели.
 */
class ImageUploadTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        Storage::fake('public');

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);
    }

    private function image(string $name = 'photo.jpg', int $w = 2400, int $h = 1800): UploadedFile
    {
        return UploadedFile::fake()->image($name, $w, $h);
    }

    // ── Логотип ──────────────────────────────────────────────

    #[Test]
    public function логотип_загружается_и_становится_видимым(): void
    {
        $this->actingAs($this->user)
            ->post('/cabinet/company/logo', ['logo' => $this->image('logo.png', 1000, 1000)])
            ->assertSessionHas('success');

        $company = $this->company->fresh();

        $this->assertNotNull($company->logo_path);
        Storage::disk('public')->assertExists($company->logo_path);

        // На витрине логотип подменяет плашку с инициалами
        $this->assertStringContainsString($company->logo_path, (string) $company->logoUrl());
    }

    /** Большое изображение ужимается: 6 МБ с камеры в каталоге не нужны. */
    #[Test]
    public function изображение_ужимается_и_переводится_в_webp(): void
    {
        $this->actingAs($this->user)->post('/cabinet/company/logo', ['logo' => $this->image('logo.jpg', 3000, 3000)]);

        $path = $this->company->fresh()->logo_path;

        $this->assertStringEndsWith('.webp', $path);

        $size = getimagesizefromstring(Storage::disk('public')->get($path));

        $this->assertLessThanOrEqual(512, $size[0], 'логотип вписывается в рамку 512×512');
        $this->assertLessThanOrEqual(512, $size[1]);
    }

    /** Замена удаляет прежний файл — иначе диск растёт от каждой правки. */
    #[Test]
    public function замена_логотипа_убирает_прежний_файл(): void
    {
        $this->actingAs($this->user)->post('/cabinet/company/logo', ['logo' => $this->image('a.png')]);
        $first = $this->company->fresh()->logo_path;

        $this->actingAs($this->user)->post('/cabinet/company/logo', ['logo' => $this->image('b.png')]);
        $second = $this->company->fresh()->logo_path;

        $this->assertNotSame($first, $second);
        Storage::disk('public')->assertMissing($first);
        Storage::disk('public')->assertExists($second);
    }

    #[Test]
    public function логотип_удаляется_и_возвращает_инициалы(): void
    {
        $this->actingAs($this->user)->post('/cabinet/company/logo', ['logo' => $this->image()]);
        $path = $this->company->fresh()->logo_path;

        $this->actingAs($this->user)->delete('/cabinet/company/logo')->assertSessionHas('success');

        $this->assertNull($this->company->fresh()->logo_path);
        $this->assertNull($this->company->fresh()->logoUrl());
        Storage::disk('public')->assertMissing($path);
    }

    /** Расширение подделывается заголовком — файл читается как изображение. */
    #[Test]
    public function подделанный_файл_не_проходит(): void
    {
        $fake = UploadedFile::fake()->create('virus.jpg', 40, 'image/jpeg');

        $this->actingAs($this->user)
            ->post('/cabinet/company/logo', ['logo' => $fake])
            ->assertSessionHas('error');

        $this->assertNull($this->company->fresh()->logo_path);
    }

    #[Test]
    public function документ_вместо_картинки_отклоняется(): void
    {
        $this->actingAs($this->user)
            ->post('/cabinet/company/logo', ['logo' => UploadedFile::fake()->create('price.pdf', 100)])
            ->assertSessionHasErrors(['logo']);
    }

    // ── Фотографии объявления ────────────────────────────────

    private function listing(): Listing
    {
        return Listing::factory()->create([
            'company_id' => $this->company->id,
            'user_id' => $this->user->id,
        ]);
    }

    #[Test]
    public function фотографии_загружаются_пачкой(): void
    {
        $listing = $this->listing();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$listing->id}/images", [
                'images' => [$this->image('1.jpg'), $this->image('2.jpg'), $this->image('3.jpg')],
            ])
            ->assertSessionHas('success');

        $images = $listing->images()->orderBy('sort')->get();

        $this->assertCount(3, $images);
        $this->assertSame([0, 1, 2], $images->pluck('sort')->all());

        foreach ($images as $image) {
            Storage::disk('public')->assertExists($image->path);
            Storage::disk('public')->assertExists($image->thumb_path);
        }
    }

    /** Миниатюра мельче полного кадра — ради неё она и делается. */
    #[Test]
    public function миниатюра_меньше_полного_изображения(): void
    {
        $listing = $this->listing();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$listing->id}/images", ['images' => [$this->image('big.jpg', 2400, 2400)]]);

        $image = $listing->images()->firstOrFail();

        $full = getimagesizefromstring(Storage::disk('public')->get($image->path));
        $thumb = getimagesizefromstring(Storage::disk('public')->get($image->thumb_path));

        $this->assertLessThan($full[0], $thumb[0]);
        $this->assertLessThanOrEqual(400, $thumb[0]);
    }

    /** Обложка — первая по порядку, отдельного флага нет. */
    #[Test]
    public function фотография_становится_обложкой(): void
    {
        $listing = $this->listing();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$listing->id}/images", [
                'images' => [$this->image('1.jpg'), $this->image('2.jpg')],
            ]);

        $second = $listing->images()->orderBy('sort')->get()->last();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$listing->id}/images/{$second->id}/cover")
            ->assertSessionHas('success');

        $this->assertSame(
            $second->id,
            $listing->images()->orderBy('sort')->first()->id,
            'выбранная фотография должна встать первой',
        );

        // Нумерация без дыр: следующая вставка «в конец» иначе попадёт в середину
        $this->assertSame([0, 1], $listing->images()->orderBy('sort')->pluck('sort')->all());
    }

    #[Test]
    public function фотография_удаляется_вместе_с_файлами(): void
    {
        $listing = $this->listing();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$listing->id}/images", ['images' => [$this->image()]]);

        $image = $listing->images()->firstOrFail();

        $this->actingAs($this->user)
            ->delete("/cabinet/listings/{$listing->id}/images/{$image->id}")
            ->assertSessionHas('success');

        $this->assertSame(0, $listing->images()->count());
        Storage::disk('public')->assertMissing($image->path);
        Storage::disk('public')->assertMissing($image->thumb_path);
    }

    /** Больше десяти никто не листает, а место они занимают. */
    #[Test]
    public function больше_десяти_фотографий_не_прикрепить(): void
    {
        $listing = $this->listing();

        $this->actingAs($this->user)->post("/cabinet/listings/{$listing->id}/images", [
            'images' => array_map(fn (int $i) => $this->image("{$i}.jpg", 400, 400), range(1, 10)),
        ]);

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$listing->id}/images", ['images' => [$this->image('extra.jpg')]])
            ->assertSessionHas('error');

        $this->assertSame(10, $listing->images()->count());
    }

    /** Чужое объявление недоступно — и о его существовании не сообщаем. */
    #[Test]
    public function к_чужому_объявлению_фото_не_прикрепить(): void
    {
        $foreign = Listing::factory()->create();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$foreign->id}/images", ['images' => [$this->image()]])
            ->assertNotFound();

        $this->assertSame(0, $foreign->images()->count());
    }

    /** Витрина показывает обложку и галерею. */
    #[Test]
    public function фотографии_видны_на_витрине(): void
    {
        $listing = Listing::factory()->create([
            'company_id' => $this->company->id,
            'user_id' => $this->user->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
        ]);

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$listing->id}/images", ['images' => [$this->image(), $this->image('2.jpg')]]);

        $this->get('/catalog')
            ->assertInertia(fn ($page) => $page->where(
                'listings.data.0.cover',
                fn (?string $url): bool => $url !== null && str_contains($url, '.webp'),
            ));

        $this->get("/listing/{$listing->fresh()->slug}")
            ->assertInertia(fn ($page) => $page->has('listing.images', 2));
    }
}
