<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Предпросмотр объявления: владелец видит свою страницу в любом
 * статусе, остальные — только опубликованную.
 *
 * Цена ошибки с обеих сторон: не показать владельцу — он публикует
 * вслепую и узнаёт о кривой карточке от покупателей; показать
 * постороннему — черновики и отклонённые модерацией тексты утекают
 * на публику до проверки.
 */
class ListingPreviewTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    private User $owner;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create();
        $this->owner = User::factory()->for($this->company)->create(['email_verified_at' => now()]);
    }

    private function draft(): Listing
    {
        return Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_DRAFT,
            'title' => 'Черновик: цемент М400 навалом',
            'views_count' => 0,
        ]);
    }

    #[Test]
    public function владелец_видит_черновик_как_предпросмотр(): void
    {
        $draft = $this->draft();

        $this->actingAs($this->owner)->get("/listing/{$draft->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('catalog/Show')
                ->where('preview', true)
                ->where('listing.title', 'Черновик: цемент М400 навалом'));
    }

    #[Test]
    public function гость_и_посторонний_не_видят_неопубликованное(): void
    {
        $draft = $this->draft();

        $this->get("/listing/{$draft->slug}")->assertNotFound();

        $stranger = User::factory()->for(Company::factory()->create())->create();
        $this->actingAs($stranger)->get("/listing/{$draft->slug}")->assertNotFound();
    }

    #[Test]
    public function опубликованное_объявление_открывается_без_плашки(): void
    {
        $listing = Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
        ]);

        $this->get("/listing/{$listing->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->where('preview', false));
    }

    /** Предпросмотр — взгляд владельца в зеркало, а не интерес покупателя. */
    #[Test]
    public function предпросмотр_не_считает_просмотры(): void
    {
        $draft = $this->draft();

        $this->actingAs($this->owner)->get("/listing/{$draft->slug}")->assertOk();

        $this->assertSame(0, $draft->fresh()->views_count);
    }
}
