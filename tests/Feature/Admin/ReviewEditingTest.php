<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Reviews\Pages\CreateReview;
use App\Filament\Resources\Reviews\Pages\EditReview;
use App\Filament\Resources\Reviews\ReviewResource;
use App\Models\Company;
use App\Models\Listing;
use App\Models\Review;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Actions\Testing\TestAction;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Правка, заведение и удаление отзывов из админки.
 *
 * Правка нужна безусловно: опечатка по просьбе автора, персональные
 * данные в тексте, клевета. Заведение — для отзывов, собранных вне
 * сайта.
 *
 * Но по отзывам покупатель решает, с кем работать, и заведённый
 * вручную обязан быть отличим от написанного покупателем. Иначе
 * рейтинг перестаёт что-либо значить, и первым это почувствует тот,
 * кто выбрал поставщика по нему.
 */
class ReviewEditingTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    private function review(array $attrs = []): Review
    {
        return Review::factory()->create($attrs);
    }

    // ── Заведение вручную ───────────────────────────────────────────

    #[Test]
    public function администратор_заводит_отзыв_через_форму(): void
    {
        $actor = $this->admin(AdminAccess::ADMIN);
        $this->actingAs($actor);

        $about = Company::factory()->create();
        $author = Company::factory()->create();

        Livewire::test(CreateReview::class)
            ->fillForm([
                'company_id' => $about->id,
                'author_company_id' => $author->id,
                'rating' => 5,
                'body' => 'Отгрузили вовремя, качество соответствует описанию.',
                'status' => Review::STATUS_PUBLISHED,
            ])
            ->call('create')
            ->assertHasNoFormErrors();

        $review = Review::query()->where('company_id', $about->id)->first();

        $this->assertNotNull($review);
        $this->assertSame(5, $review->rating);
    }

    /**
     * Происхождение проставляет код, а не форма.
     *
     * Поле, которым можно выдать заведённый отзыв за покупательский,
     * обесценило бы саму пометку.
     */
    #[Test]
    public function заведённый_вручную_помечается_происхождением(): void
    {
        $actor = $this->admin(AdminAccess::ADMIN);
        $this->actingAs($actor);

        Livewire::test(CreateReview::class)
            ->fillForm([
                'company_id' => Company::factory()->create()->id,
                'author_company_id' => Company::factory()->create()->id,
                'rating' => 4,
                'body' => 'Работали дважды, оба раза без нареканий.',
                'status' => Review::STATUS_PUBLISHED,
            ])
            ->call('create')
            ->assertHasNoFormErrors();

        $review = Review::query()->latest('id')->first();

        $this->assertSame(Review::ORIGIN_ADMIN, $review->origin);
        $this->assertSame($actor->id, $review->created_by, 'должно быть видно, кто завёл');
    }

    /** Отзыв компании о самой себе — не отзыв. */
    #[Test]
    public function компания_не_отзывается_о_себе(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));
        $company = Company::factory()->create();

        Livewire::test(CreateReview::class)
            ->fillForm([
                'company_id' => $company->id,
                'author_company_id' => $company->id,
                'rating' => 5,
                'body' => 'Прекрасная компания, рекомендуем сами себя.',
                'status' => Review::STATUS_PUBLISHED,
            ])
            ->call('create')
            ->assertHasFormErrors(['author_company_id']);
    }

    /** Отзыв покупателя пометку не получает. */
    #[Test]
    public function отзыв_покупателя_остаётся_покупательским(): void
    {
        $this->assertSame(Review::ORIGIN_BUYER, $this->review()->origin);
    }

    // ── Правка ──────────────────────────────────────────────────────

    #[Test]
    public function администратор_правит_текст_отзыва(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));
        $review = $this->review(['body' => 'Тут был номер телефона +998 90 123-45-67']);

        Livewire::test(EditReview::class, ['record' => $review->getRouteKey()])
            ->assertOk()
            ->fillForm(['body' => 'Текст без личных данных, всё остальное как было.'])
            ->call('save')
            ->assertHasNoFormErrors();

        $this->assertSame('Текст без личных данных, всё остальное как было.', $review->fresh()->body);
    }

    /** Правка не переписывает происхождение: отзыв покупателя им и остаётся. */
    #[Test]
    public function правка_не_меняет_происхождение(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));
        $review = $this->review();

        Livewire::test(EditReview::class, ['record' => $review->getRouteKey()])
            ->fillForm(['body' => 'Поправленный текст отзыва, достаточно длинный.'])
            ->call('save')
            ->assertHasNoFormErrors();

        $this->assertSame(Review::ORIGIN_BUYER, $review->fresh()->origin);
    }

    // ── Удаление ────────────────────────────────────────────────────

    /** Удаление данных — суперадминское право, как и везде в панели. */
    #[Test]
    public function удалять_отзывы_может_только_суперадмин(): void
    {
        $review = $this->review();

        $this->actingAs($this->admin(AdminAccess::MODERATOR));
        $this->assertFalse(ReviewResource::canDelete($review));

        $this->actingAs($this->admin(AdminAccess::ADMIN));
        $this->assertFalse(ReviewResource::canDelete($review));

        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));
        $this->assertTrue(ReviewResource::canDelete($review));
    }

    /**
     * Удаление проверяется со страницы правки: оттуда после удаления
     * идёт переход в список, и это обычный путь. В таблице то же
     * действие после удаления пытается перерисовать исчезнувшую
     * строку — проверка ловила бы Livewire, а не удаление.
     */
    #[Test]
    public function суперадмин_удаляет_отзыв(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));
        $review = $this->review();

        Livewire::test(EditReview::class, ['record' => $review->getRouteKey()])
            ->callAction(TestAction::make('delete'));

        $this->assertDatabaseMissing('reviews', ['id' => $review->id]);
    }

    // ── Доступ к загрузке ───────────────────────────────────────────

    /**
     * Загрузка пачкой двигает рейтинг сильнее, чем месяц работы
     * модератора, — поэтому она отдельное право и не у него.
     */
    #[Test]
    public function загружать_отзывы_файлом_может_не_каждый(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));
        $this->assertTrue(AdminAccess::allows('reviews.import'));

        $this->actingAs($this->admin(AdminAccess::ADMIN));
        $this->assertTrue(AdminAccess::allows('reviews.import'));

        $this->actingAs($this->admin(AdminAccess::MODERATOR));
        $this->assertFalse(AdminAccess::allows('reviews.import'), 'модератор отзывы файлом не грузит');

        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));
        $this->assertFalse(AdminAccess::allows('reviews.import'));
    }

    // ── Рейтинг компании ────────────────────────────────────────────

    /**
     * Заведённый отзыв обязан двигать рейтинг.
     *
     * Пересчёт звала только модерация, а отзывы теперь приходят ещё
     * тремя путями. Без этого администратор заводил отзыв на пять
     * звёзд, а оценка компании на сайте оставалась прежней — и фича
     * выглядела бы сломанной.
     */
    #[Test]
    public function заведённый_отзыв_двигает_рейтинг_компании(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $about = Company::factory()->create(['rating' => 0, 'reviews_count' => 0]);

        Livewire::test(CreateReview::class)
            ->fillForm([
                'company_id' => $about->id,
                'author_company_id' => Company::factory()->create()->id,
                'rating' => 5,
                'body' => 'Отгрузили вовремя, качество соответствует описанию.',
                'status' => Review::STATUS_PUBLISHED,
            ])
            ->call('create')
            ->assertHasNoFormErrors();

        $this->assertSame(1, $about->fresh()->reviews_count);
        $this->assertGreaterThan(0, (float) $about->fresh()->rating);
    }

    /** Удалённый отзыв уходит из рейтинга — иначе оценка держится на призраке. */
    #[Test]
    public function удалённый_отзыв_уходит_из_рейтинга(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $review = $this->review(['status' => Review::STATUS_PUBLISHED, 'rating' => 5]);
        $company = $review->company;

        $this->assertSame(1, $company->fresh()->reviews_count);

        Livewire::test(EditReview::class, ['record' => $review->getRouteKey()])
            ->callAction(TestAction::make('delete'));

        $this->assertSame(0, $company->fresh()->reviews_count);
    }

    /** Правка опечатки рейтинг не трогает: пересчитывается только то, что влияет. */
    #[Test]
    public function правка_текста_рейтинг_не_меняет(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $review = $this->review(['status' => Review::STATUS_PUBLISHED, 'rating' => 4]);
        $before = (float) $review->company->fresh()->rating;

        Livewire::test(EditReview::class, ['record' => $review->getRouteKey()])
            ->fillForm(['body' => 'Тот же смысл, исправлена опечатка в слове.'])
            ->call('save')
            ->assertHasNoFormErrors();

        $this->assertSame($before, (float) $review->company->fresh()->rating);
    }

    // ── Повтор пары ─────────────────────────────────────────────────

    /**
     * Два отзыва одной компании о другой — это удвоенный голос
     * в рейтинге, по которому покупатель выбирает поставщика.
     * Раньше форма заводила такой отзыв молча.
     */
    #[Test]
    public function второй_отзыв_той_же_пары_не_заводится(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $about = Company::factory()->create();
        $author = Company::factory()->create();

        $this->review([
            'company_id' => $about->id,
            'author_company_id' => $author->id,
            'listing_id' => null,
            'status' => Review::STATUS_PUBLISHED,
        ]);

        Livewire::test(CreateReview::class)
            ->fillForm([
                'company_id' => $about->id,
                'author_company_id' => $author->id,
                'rating' => 5,
                'body' => 'Второй отзыв от той же компании о той же компании.',
                'status' => Review::STATUS_PUBLISHED,
            ])
            ->call('create')
            ->assertHasFormErrors(['author_company_id']);

        $this->assertSame(1, Review::query()
            ->where('company_id', $about->id)
            ->where('author_company_id', $author->id)
            ->count());
    }

    /**
     * Повтор пары с объявлением индекс ловил, но ошибкой базы:
     * администратор получал пятисотую страницу и терял набранный текст.
     */
    #[Test]
    public function повтор_пары_с_объявлением_отвечает_ошибкой_поля(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $about = Company::factory()->create();
        $author = Company::factory()->create();
        $listing = Listing::factory()->create(['company_id' => $about->id]);

        $this->review([
            'company_id' => $about->id,
            'author_company_id' => $author->id,
            'listing_id' => $listing->id,
            'status' => Review::STATUS_PUBLISHED,
        ]);

        Livewire::test(CreateReview::class)
            ->fillForm([
                'company_id' => $about->id,
                'author_company_id' => $author->id,
                'listing_id' => $listing->id,
                'rating' => 5,
                'body' => 'Повтор пары автор — компания — объявление.',
                'status' => Review::STATUS_PUBLISHED,
            ])
            ->call('create')
            ->assertHasFormErrors(['author_company_id']);
    }

    /**
     * Последний рубеж — сама база.
     *
     * Индекс на (компания, автор, объявление) обещал «один отзыв
     * на пару», но у отзыва о компании вообще объявления нет, а NULL
     * в уникальном индексе не равен NULL. Перехват ошибки базы
     * в ReviewService — защита от двойного нажатия — не мог сработать
     * ни разу, потому что ошибки не было.
     */
    #[Test]
    public function база_не_даёт_завести_второй_отзыв_о_компании(): void
    {
        $about = Company::factory()->create();
        $author = Company::factory()->create();

        $this->review([
            'company_id' => $about->id,
            'author_company_id' => $author->id,
            'listing_id' => null,
        ]);

        $this->expectException(UniqueConstraintViolationException::class);

        $this->review([
            'company_id' => $about->id,
            'author_company_id' => $author->id,
            'listing_id' => null,
        ]);
    }
}
