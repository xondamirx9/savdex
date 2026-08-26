<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Database\Seeders\CategorySeeder;
use Database\Seeders\ShowcaseSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Storage;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Наполнение витрины: описания пустым карточкам компаний и картинки
 * объявлениям без фотографий.
 *
 * Сидер запускают и на живой базе, поэтому проверяется главное
 * обещание: он только дополняет — не перезаписывает заполненное,
 * не трогает черновики и не дублирует при повторном запуске.
 */
class ShowcaseSeederTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    private User $user;

    protected function setUp(): void
    {
        parent::setUp();

        Storage::fake('public');
        $this->seed(CategorySeeder::class);

        $this->company = Company::factory()->create(['description' => null]);
        $this->user = User::factory()->for($this->company)->create();
    }

    private function listing(array $overrides = []): Listing
    {
        return Listing::create(array_merge([
            'company_id' => $this->company->id,
            'user_id' => $this->user->id,
            'category_id' => Category::where('slug', 'cement-beton')->value('id'),
            'status' => Listing::STATUS_ACTIVE,
            'type' => Listing::TYPE_SUPPLY,
            'title' => 'Цемент М400 навалом, отгрузка с завода',
            'currency' => 'UZS',
        ], $overrides));
    }

    #[Test]
    public function пустая_карточка_компании_получает_описание(): void
    {
        $this->listing();

        $this->seed(ShowcaseSeeder::class);

        $description = (string) $this->company->fresh()->description;

        // Порог профиля — 100 знаков: короче для карточки недостаточно
        $this->assertGreaterThanOrEqual(100, mb_strlen($description));
        $this->assertStringContainsString('цемент м400 навалом', $description);
    }

    #[Test]
    public function заполненное_описание_не_перезаписывается(): void
    {
        $this->company->forceFill(['description' => 'Наш собственный текст о компании.'])->save();

        $this->seed(ShowcaseSeeder::class);

        $this->assertSame('Наш собственный текст о компании.', $this->company->fresh()->description);
    }

    #[Test]
    public function объявление_без_фото_получает_картинки(): void
    {
        $listing = $this->listing();

        $this->seed(ShowcaseSeeder::class);

        $images = $listing->images()->orderBy('sort')->get();

        $this->assertCount(3, $images);

        foreach ($images as $image) {
            Storage::disk('public')->assertExists($image->path);
            $this->assertStringStartsWith('<svg', (string) Storage::disk('public')->get($image->path));
        }
    }

    /** Свои фотографии дороже сгенерированных: занятые объявления пропускаются. */
    #[Test]
    public function объявление_со_своими_фото_не_трогается(): void
    {
        $listing = $this->listing();
        $listing->images()->create(['path' => 'listings/own.jpg', 'thumb_path' => 'listings/own.jpg', 'sort' => 0]);

        $this->seed(ShowcaseSeeder::class);

        $this->assertSame(1, $listing->images()->count());
    }

    /** Черновик ещё редактируют — подставлять в него картинки рано. */
    #[Test]
    public function черновики_остаются_без_картинок(): void
    {
        $draft = $this->listing(['status' => Listing::STATUS_DRAFT, 'title' => 'Черновик']);

        $this->seed(ShowcaseSeeder::class);

        $this->assertSame(0, $draft->images()->count());
    }

    /** Деплой стирал файлы контейнера: запись в базе есть, файла нет. */
    #[Test]
    public function пропавший_файл_картинки_восстанавливается(): void
    {
        $listing = $this->listing();

        $this->seed(ShowcaseSeeder::class);

        $image = $listing->images()->firstOrFail();
        Storage::disk('public')->delete($image->path);

        $this->seed(ShowcaseSeeder::class);

        Storage::disk('public')->assertExists($image->path);
        $this->assertSame(3, $listing->images()->count());
    }

    #[Test]
    public function повторный_запуск_ничего_не_дублирует(): void
    {
        $listing = $this->listing();

        $this->seed(ShowcaseSeeder::class);
        $description = $this->company->fresh()->description;

        $this->seed(ShowcaseSeeder::class);

        $this->assertSame(3, $listing->images()->count());
        $this->assertSame($description, $this->company->fresh()->description);
    }
}
