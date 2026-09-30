<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Listing;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Загруженное из книги объявление видно на всех языках.
 *
 * Раньше без перевода заголовка на языке оно скрывалось, и на турецкой
 * версии каталог с сотнями загруженных заявок стоял пустым, пока
 * переводчик не доберётся до каждой. Теперь до перевода показывается
 * русский текст — как у написанного в кабинете, — а готовый перевод
 * подставляется сам.
 */
class ImportedListingVisibilityTest extends TestCase
{
    use RefreshDatabase;

    private function imported(array $overrides = []): Listing
    {
        return Listing::factory()->create([
            'company_id' => Company::factory()->create(['status' => 'active'])->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'expires_at' => now()->addDays(30),
            'source' => Listing::SOURCE_IMPORT,
            'title' => 'Кирпич керамический М150',
            ...$overrides,
        ]);
    }

    #[Test]
    public function загруженное_без_перевода_видно_на_всех_языках_русским_текстом(): void
    {
        $this->imported(['title_i18n' => ['uz' => 'Keramik g‘isht M150']]);

        foreach (['/catalog', '/en/catalog', '/tr/catalog', '/zh/catalog'] as $path) {
            $this->get($path)->assertInertia(fn (AssertableInertia $page) => $page
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Кирпич керамический М150'));
        }

        // Перевод есть — показывается он
        $this->get('/uz/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.title', 'Keramik g‘isht M150'));
    }

    #[Test]
    public function страница_загруженного_объявляет_все_языки(): void
    {
        $listing = $this->imported();

        $this->assertSame(['ru', 'uz', 'en', 'zh', 'tr'], array_values(array_intersect(
            ['ru', 'uz', 'en', 'zh', 'tr'],
            $listing->visibleLocales(),
        )));

        $this->get('/tr/listing/'.$listing->slug)->assertOk();
    }
}
