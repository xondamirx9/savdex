<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\PlatformReview;
use App\Models\Review;
use App\Models\Setting;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Отзывы о площадке, лента «Все отзывы» и просьбы оставить отзыв.
 *
 * Отзывы пишут только сами пользователи: вход, подтверждённая почта,
 * проверка модератором. Лента показывает только опубликованное, а
 * просьба приходит каждому один раз.
 */
class PlatformReviewsTest extends TestCase
{
    use RefreshDatabase;

    private const BODY = 'Нашли двух поставщиков цемента за неделю, всё понятно и удобно.';

    private function review(array $attributes = []): PlatformReview
    {
        // Дата — мимо fillable: в жизни её ставит сама база
        $review = new PlatformReview;
        $review->forceFill([
            'user_id' => User::factory()->create()->id,
            'rating' => 5,
            'body' => self::BODY,
            'status' => PlatformReview::STATUS_PUBLISHED,
            ...$attributes,
        ])->save();

        return $review;
    }

    // ── Форма «Оцените SavdEx» ───────────────────────────────

    #[Test]
    public function гостя_форма_отправляет_на_вход(): void
    {
        $this->get('/reviews/new')->assertRedirect('/login');
        $this->post('/reviews/new', ['rating' => 5, 'body' => self::BODY])->assertRedirect('/login');

        $this->assertSame(0, PlatformReview::count());
    }

    #[Test]
    public function отзыв_уходит_на_проверку_и_правится_без_второй_записи(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)
            ->post('/reviews/new', ['rating' => 4, 'rating_support' => 5, 'body' => self::BODY])
            ->assertSessionHas('success');

        $review = PlatformReview::sole();
        $this->assertSame(PlatformReview::STATUS_MODERATION, $review->status);
        $this->assertSame(5, $review->rating_support);
        $this->assertNull($review->rating_search);

        // Правка опубликованного — снова на проверку, та же запись
        $review->forceFill(['status' => PlatformReview::STATUS_PUBLISHED])->save();

        $this->actingAs($user)->post('/reviews/new', ['rating' => 2, 'body' => self::BODY.' Но поддержка отвечает долго.']);

        $this->assertSame(1, PlatformReview::count());
        $this->assertSame(PlatformReview::STATUS_MODERATION, $review->fresh()->status);
        $this->assertSame(2, $review->fresh()->rating);

        $this->actingAs($user)->get('/reviews/new')->assertInertia(fn (AssertableInertia $page) => $page
            ->component('reviews/Leave')
            ->where('review.rating', 2)
            ->where('review.status', PlatformReview::STATUS_MODERATION)
            ->where('blocked', null)
        );
    }

    #[Test]
    public function без_подтверждённой_почты_отзыв_не_принимается(): void
    {
        $user = User::factory()->unverified()->create();

        $this->actingAs($user)->post('/reviews/new', ['rating' => 5, 'body' => self::BODY])->assertSessionHas('error');

        $this->assertSame(0, PlatformReview::count());
    }

    #[Test]
    public function короткий_текст_и_оценка_проверяются(): void
    {
        $this->actingAs(User::factory()->create())
            ->post('/reviews/new', ['rating' => 0, 'body' => 'Норм'])
            ->assertSessionHasErrors(['rating', 'body']);
    }

    #[Test]
    public function без_премодерации_чистый_текст_публикуется_сразу_а_с_телефоном_нет(): void
    {
        Setting::create(['key' => 'reviews_premoderation', 'group' => 'reviews', 'label' => 'x', 'type' => 'bool', 'value' => false]);
        Setting::flushCache();

        $this->actingAs(User::factory()->create())->post('/reviews/new', ['rating' => 5, 'body' => self::BODY]);
        $this->actingAs(User::factory()->create())->post('/reviews/new', [
            'rating' => 5,
            'body' => self::BODY.' Звоните мне: +998 90 123 45 67',
        ]);

        [$clean, $flagged] = PlatformReview::orderBy('id')->get()->all();
        $this->assertSame(PlatformReview::STATUS_PUBLISHED, $clean->status);
        $this->assertSame(PlatformReview::STATUS_MODERATION, $flagged->status);
        $this->assertNotNull($flagged->screening_flags);
    }

    // ── Модерация ────────────────────────────────────────────

    // ── Лента ────────────────────────────────────────────────

    #[Test]
    public function страница_отзывов_сводка_вкладки_и_только_опубликованное(): void
    {
        $this->review(['rating' => 5, 'rating_usability' => 4, 'created_at' => now()->subDays(3)]);
        $this->review(['rating' => 2, 'rating_usability' => 5, 'created_at' => now()->subDays(2)]);
        $this->review(['status' => PlatformReview::STATUS_MODERATION]);
        $this->review(['status' => PlatformReview::STATUS_HIDDEN]);

        Review::factory()->create(['rating' => 4, 'status' => 'published', 'created_at' => now()->subDay()]);
        Review::factory()->create(['status' => 'moderation']);
        // Отзыв о заблокированной компании в ленту не попадает
        Review::factory()->create([
            'status' => 'published',
            'company_id' => Company::factory()->blocked()->create()->id,
        ]);

        $this->get('/reviews')->assertOk()->assertInertia(fn (AssertableInertia $page) => $page
            ->component('Reviews')
            ->where('summary.count', 2)
            ->where('summary.average', 3.5)
            ->where('summary.stars.0', ['star' => 5, 'count' => 1])
            ->where('summary.stars.3', ['star' => 2, 'count' => 1])
            ->where('summary.criteria.0.average', 4.5)
            ->where('summary.criteria.1.average', null)
            ->where('counts', ['all' => 3, 'platform' => 2, 'company' => 1])
            ->has('reviews', 3)
            ->where('reviews.0.kind', 'company')
            ->where('reviews.1.kind', 'platform')
            ->where('reviews.1.rating', 2)
        );

        $this->get('/reviews?type=platform')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('type', 'platform')
            ->has('reviews', 2)
            ->where('reviews.0.company_slug', null)
        );

        $this->get('/reviews?type=nonsense&page=-3')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('type', 'all')
            ->where('page', 1)
        );
    }

    #[Test]
    public function лента_по_страницам_без_пропусков_и_повторов(): void
    {
        foreach (range(1, 25) as $i) {
            $this->review(['created_at' => now()->subMinutes($i)]);
        }

        $ids = [];

        foreach ([1, 2] as $page) {
            $this->get("/reviews?page={$page}")->assertInertia(function (AssertableInertia $p) use (&$ids): void {
                $ids = [...$ids, ...array_column($p->toArray()['props']['reviews'], 'id')];
                $p->where('pages', 2);
            });
        }

        $this->assertCount(25, array_unique($ids));
    }

    #[Test]
    public function подпись_автора_компания_или_имя_с_буквой_фамилии(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Цемент Трейд»']);
        $this->review(['user_id' => User::factory()->create(['name' => 'Азиз Каримов'])->id, 'created_at' => now()->subMinute()]);
        $this->review(['user_id' => User::factory()->create()->id, 'company_id' => $company->id]);

        $this->get('/reviews?type=platform')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('reviews.0.author', 'ООО «Цемент Трейд»')
            ->where('reviews.0.initials', 'ЦТ')
            ->where('reviews.1.author', 'Азиз К.')
            ->where('reviews.1.initials', 'АК')
        );
    }

    #[Test]
    public function на_главной_три_свежих_отзыва_обоих_видов(): void
    {
        $this->review(['created_at' => now()->subDays(5)]);
        $this->review(['created_at' => now()->subDay()]);
        Review::factory()->create(['status' => 'published', 'created_at' => now()->subHours(2)]);
        Review::factory()->create(['status' => 'published', 'created_at' => now()->subDays(3)]);

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page
            ->has('reviews', 3)
            ->where('reviews.0.kind', 'company')
            ->where('reviews.1.kind', 'platform')
            ->where('reviews.2.kind', 'company')
        );
    }

    // ── Просьбы оставить отзыв ───────────────────────────────

    #[Test]
    public function просьба_оценить_площадку_через_неделю_и_один_раз(): void
    {
        $old = User::factory()->create(['created_at' => now()->subDays(8)]);
        $fresh = User::factory()->create(['created_at' => now()->subDays(2)]);
        $reviewed = User::factory()->create(['created_at' => now()->subDays(30)]);
        $this->review(['user_id' => $reviewed->id]);

        $this->artisan('reviews:ask')->assertSuccessful();
        $this->artisan('reviews:ask')->assertSuccessful();

        $this->assertSame(1, $old->alerts()->where('type', 'platform_review_ask')->count());
        $this->assertSame('/reviews/new', $old->alerts()->first()->url);
        $this->assertSame(0, $fresh->alerts()->count());
        $this->assertSame(0, $reviewed->alerts()->count());
    }

    #[Test]
    public function просьба_отзыва_о_компании_после_раскрытия_контактов(): void
    {
        $buyer = User::factory()->for(Company::factory())->create(['created_at' => now()->subDay()]);
        $target = Company::factory()->create();
        ContactUnlock::factory()->create([
            'company_id' => $buyer->company_id,
            'target_company_id' => $target->id,
            'user_id' => $buyer->id,
            'created_at' => now()->subDays(4),
        ]);

        // Свежее раскрытие — рано, отзыв уже есть — незачем
        $reviewedTarget = Company::factory()->create();
        ContactUnlock::factory()->create([
            'company_id' => $buyer->company_id,
            'target_company_id' => $reviewedTarget->id,
            'user_id' => $buyer->id,
            'created_at' => now()->subDays(5),
        ]);
        Review::factory()->create(['company_id' => $reviewedTarget->id, 'author_company_id' => $buyer->company_id]);
        ContactUnlock::factory()->create([
            'company_id' => $buyer->company_id,
            'user_id' => $buyer->id,
            'created_at' => now()->subDay(),
        ]);

        $this->artisan('reviews:ask')->assertSuccessful();
        $this->artisan('reviews:ask')->assertSuccessful();

        $asks = $buyer->alerts()->where('type', 'review_ask')->get();
        $this->assertCount(1, $asks);
        $this->assertSame('/company/'.$target->slug.'#reviews', $asks->first()->url);
        $this->assertStringContainsString($target->name, $asks->first()->title);
    }
}
