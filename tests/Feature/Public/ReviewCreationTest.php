<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Review;
use App\Models\Setting;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Создание отзывов.
 *
 * До этого отзывы существовали только в сидерах: страницы показывали
 * рейтинг и число отзывов, каталог по рейтингу сортировал, а оставить
 * отзыв было нельзя ни одним способом. Для площадки, продающей доверие,
 * это означало, что главный трастовый показатель ничем не обеспечен.
 */
class ReviewCreationTest extends TestCase
{
    use RefreshDatabase;

    private User $buyer;

    private Company $buyerCompany;

    private Company $supplier;

    protected function setUp(): void
    {
        parent::setUp();

        $this->buyerCompany = Company::factory()->create(['name' => 'ООО «Закупщик»']);
        $this->buyer = User::factory()->for($this->buyerCompany)->create(['email_verified_at' => now()]);
        $this->supplier = Company::factory()->create(['name' => 'ООО «Поставщик»']);

        /*
         * Премодерация выключена: этот набор проверяет правила «кто
         * и когда может оставить отзыв». Что происходит с отзывом
         * после отправки — предмет ReviewPremoderationTest.
         */
        Setting::updateOrCreate(
            ['key' => 'reviews_premoderation'],
            ['group' => 'moderation', 'label' => 'Премодерация', 'type' => 'boolean', 'value' => false],
        );
    }

    private function unlocked(): void
    {
        ContactUnlock::create([
            'company_id' => $this->buyerCompany->id,
            'target_company_id' => $this->supplier->id,
            'user_id' => $this->buyer->id,
            'credits_spent' => 1,
            'status' => 'new',
        ]);
    }

    /** @param array<string, mixed> $overrides */
    private function payload(array $overrides = []): array
    {
        return [
            'rating' => 5,
            'body' => 'Отгрузили цемент в срок, документы прислали в тот же день. Работаем второй раз.',
            'deal_confirmed' => true,
            ...$overrides,
        ];
    }

    #[Test]
    public function оплативший_контакт_оставляет_отзыв(): void
    {
        $this->unlocked();

        $this->actingAs($this->buyer)
            ->post("/company/{$this->supplier->slug}/review", $this->payload())
            ->assertSessionHas('success');

        $review = Review::where('company_id', $this->supplier->id)->first();

        $this->assertNotNull($review);
        $this->assertSame(5, $review->rating);
        $this->assertSame($this->buyerCompany->id, $review->author_company_id);
        $this->assertTrue($review->deal_confirmed);
    }

    /**
     * Главное правило: без оплаченного раскрытия отзыв не принимается.
     * Иначе рейтинг конкурента опускается за вечер и бесплатно.
     */
    #[Test]
    public function без_раскрытия_контактов_отзыв_не_принимается(): void
    {
        $this->actingAs($this->buyer)
            ->post("/company/{$this->supplier->slug}/review", $this->payload())
            ->assertSessionHas('error');

        $this->assertSame(0, Review::count());
    }

    #[Test]
    public function второй_отзыв_той_же_компании_не_принимается(): void
    {
        $this->unlocked();

        $this->actingAs($this->buyer)->post("/company/{$this->supplier->slug}/review", $this->payload());

        $this->actingAs($this->buyer)
            ->post("/company/{$this->supplier->slug}/review", $this->payload(['rating' => 1]))
            ->assertSessionHas('error');

        $this->assertSame(1, Review::count());
    }

    #[Test]
    public function себе_отзыв_не_оставить(): void
    {
        $owner = User::factory()->for($this->supplier)->create(['email_verified_at' => now()]);

        $this->actingAs($owner)
            ->post("/company/{$this->supplier->slug}/review", $this->payload())
            ->assertSessionHas('error');

        $this->assertSame(0, Review::count());
    }

    #[Test]
    public function отзыв_из_двух_слов_не_принимается(): void
    {
        $this->unlocked();

        $this->actingAs($this->buyer)
            ->post("/company/{$this->supplier->slug}/review", $this->payload(['body' => 'Всё ок']))
            ->assertSessionHasErrors(['body']);

        $this->assertSame(0, Review::count());
    }

    /**
     * Рейтинг пересчитывается сразу: ночного задания человек не дождётся.
     *
     * Проверяется на фоне чужих троек — иначе средняя по площадке равна
     * единственной оценке, и байесовская формула вырождается в неё же.
     * Смысл формулы как раз в том, что один отзыв не уводит компанию
     * далеко от среднего по площадке.
     */
    #[Test]
    public function рейтинг_компании_обновляется_сразу(): void
    {
        $background = Company::factory()->create();

        Review::factory()->count(4)->create([
            'company_id' => $background->id,
            'rating' => 3,
            'status' => 'published',
        ]);

        $this->unlocked();
        $this->actingAs($this->buyer)->post("/company/{$this->supplier->slug}/review", $this->payload());

        $supplier = $this->supplier->fresh();

        $this->assertSame(1, $supplier->reviews_count);
        $this->assertGreaterThan(3.4, (float) $supplier->rating, 'оценка «5» поднимает рейтинг выше среднего');
        $this->assertLessThan(4.0, (float) $supplier->rating, 'но один отзыв не даёт пять звёзд');
    }

    #[Test]
    public function компания_узнаёт_о_новом_отзыве(): void
    {
        $this->unlocked();
        $owner = User::factory()->for($this->supplier)->create();

        $this->actingAs($this->buyer)->post("/company/{$this->supplier->slug}/review", $this->payload());

        $this->assertSame(1, $owner->alerts()->count());
    }

    #[Test]
    public function гость_отзыв_не_оставит(): void
    {
        $this->post("/company/{$this->supplier->slug}/review", $this->payload())
            ->assertRedirect('/login');

        $this->assertSame(0, Review::count());
    }

    /** Визитка объясняет причину отказа до того, как человек напишет текст. */
    #[Test]
    public function визитка_отдаёт_причину_запрета(): void
    {
        $this->actingAs($this->buyer)
            ->get("/company/{$this->supplier->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('review_blocked', fn (?string $reason): bool => $reason !== null
                    && str_contains($reason, 'раскрытия контактов')),
            );
    }

    #[Test]
    public function визитка_показывает_опубликованные_отзывы(): void
    {
        $this->unlocked();
        $this->actingAs($this->buyer)->post("/company/{$this->supplier->slug}/review", $this->payload());

        $this->get("/company/{$this->supplier->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('reviews', 1)
                ->where('reviews.0.author', 'ООО «Закупщик»')
                ->where('reviews.0.rating', 5),
            );
    }
}
