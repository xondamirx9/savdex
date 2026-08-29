<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Публикация объявления.
 *
 * Предварительной модерации нет: «Опубликовать» сразу выводит
 * объявление на витрину, контроль — постмодерацией. Кнопка стоит
 * на последнем шаге мастера, а проверяется объявление целиком:
 * когда описание короче тридцати знаков, сервер возвращал ошибку
 * по полю второго шага — и на четвёртом её негде было показать.
 */
class ListingPublishTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Company $company;

    private Category $category;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create();
        $this->category = Category::factory()->named('Кирпич')->create();
    }

    /** @param array<string, mixed> $overrides */
    private function draft(array $overrides = []): Listing
    {
        return Listing::factory()->draft()->create([
            'company_id' => $this->company->id,
            'user_id' => $this->user->id,
            ...$overrides,
        ]);
    }

    /** @return array<string, mixed> */
    private function payload(array $overrides = []): array
    {
        return [
            'category_id' => $this->category->id,
            'title' => 'Кирпич керамический полнотелый М150',
            'description' => 'Полнотелый керамический кирпич марки М150. Отгрузка с завода в Ташкенте, паллеты по 300 штук.',
            'price' => 1200,
            'currency' => 'UZS',
            'price_negotiable' => false,
            ...$overrides,
        ];
    }

    #[Test]
    public function заполненный_черновик_публикуется_сразу(): void
    {
        $draft = $this->draft();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$draft->id}/publish", $this->payload())
            ->assertRedirect('/cabinet/listings')
            ->assertSessionHas('success');

        $draft->refresh();

        $this->assertSame(Listing::STATUS_ACTIVE, $draft->status);
        $this->assertNotNull($draft->published_at);
        $this->assertTrue($draft->expires_at->isFuture());
        $this->assertNotEmpty($draft->slug, 'адрес нужен, чтобы объявление открывалось на витрине');

        // И правда на витрине: страница отвечает без предпросмотра
        $this->get("/listing/{$draft->slug}")->assertOk();
    }

    /**
     * Короткое описание — самая частая причина отказа публикации.
     * Черновик при этом должен уцелеть: терять набранный текст
     * из-за одной непройденной проверки нельзя.
     */
    #[Test]
    public function короткое_описание_возвращает_ошибку_и_не_теряет_черновик(): void
    {
        $draft = $this->draft(['title' => 'Старый заголовок']);

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$draft->id}/publish", $this->payload(['description' => 'Кирпич есть']))
            ->assertSessionHasErrors(['description']);

        $draft->refresh();

        $this->assertSame(Listing::STATUS_DRAFT, $draft->status);
        $this->assertSame('Старый заголовок', $draft->title);
    }

    /** Цена обязательна, пока не отмечено «договорная». */
    #[Test]
    public function без_цены_и_без_отметки_договорная_публикация_не_проходит(): void
    {
        $draft = $this->draft();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$draft->id}/publish", $this->payload(['price' => null]))
            ->assertSessionHasErrors(['price']);

        $this->assertSame(Listing::STATUS_DRAFT, $draft->fresh()->status);
    }

    #[Test]
    public function с_отметкой_договорная_цена_не_нужна(): void
    {
        $draft = $this->draft();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$draft->id}/publish", $this->payload([
                'price' => null,
                'price_negotiable' => true,
            ]))
            ->assertSessionHasNoErrors();

        $this->assertSame(Listing::STATUS_ACTIVE, $draft->fresh()->status);
    }

    /**
     * Отклонённое объявление публикуется заново в один клик — тоже
     * без очереди, но с проверкой лимита тарифа: иначе отклонение
     * и повторная публикация обходили бы его.
     */
    #[Test]
    public function отклонённое_публикуется_заново_сразу(): void
    {
        $rejected = $this->draft(['status' => Listing::STATUS_REJECTED, 'moderation_note' => 'Мало данных']);

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$rejected->id}/resubmit")
            ->assertSessionHas('success');

        $rejected->refresh();

        $this->assertSame(Listing::STATUS_ACTIVE, $rejected->status);
        $this->assertNull($rejected->moderation_note);
    }

    /**
     * Мастер возвращается с ошибками на тот же экран — значит, статус
     * черновика должен в нём быть, иначе интерфейс не поймёт,
     * что показывать.
     */
    #[Test]
    public function мастер_отдаёт_статус_черновика(): void
    {
        $draft = $this->draft();

        $this->actingAs($this->user)
            ->get("/cabinet/listings/{$draft->id}/edit")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('cabinet/listings/Wizard')
                ->where('listing.status', Listing::STATUS_DRAFT),
            );
    }

    /** Автосохранение хранит черновик как есть — проверок здесь нет. */
    #[Test]
    public function автосохранение_принимает_недописанный_черновик(): void
    {
        $draft = $this->draft();

        $this->actingAs($this->user)
            ->postJson("/cabinet/listings/{$draft->id}/autosave", [
                'title' => 'Кир',
                'description' => 'Ещё думаю',
                'step' => 2,
            ])
            ->assertOk()
            ->assertJsonStructure(['saved_at']);

        $draft->refresh();

        $this->assertSame('Кир', $draft->title);
        $this->assertSame(2, $draft->wizard_step);
        $this->assertSame(Listing::STATUS_DRAFT, $draft->status);
    }

    /** Чужой черновик опубликовать нельзя — и о его существовании не сообщаем. */
    #[Test]
    public function чужой_черновик_недоступен(): void
    {
        $foreign = Listing::factory()->draft()->create();

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$foreign->id}/publish", $this->payload())
            ->assertNotFound();

        $this->assertSame(Listing::STATUS_DRAFT, $foreign->fresh()->status);
    }
}
