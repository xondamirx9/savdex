<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Filament\Resources\Reviews\Pages\ListReviews;
use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Review;
use App\Models\Setting;
use App\Models\User;
use App\Support\ReviewScreening;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Премодерация отзывов.
 *
 * Отзыв — единственное место, где чужой текст попадает на витрину
 * без правки. Проверка каждого перед публикацией включается настройкой,
 * а автоматический отбор работает всегда: отзыв с контактами внутри
 * раздаёт бесплатно то, что на площадке продаётся за кредиты, и
 * пускать такое на страницу нельзя ни при каких настройках.
 */
class ReviewPremoderationTest extends TestCase
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
        $this->supplier = Company::factory()->create();

        ContactUnlock::create([
            'company_id' => $this->buyerCompany->id,
            'target_company_id' => $this->supplier->id,
            'user_id' => $this->buyer->id,
            'credits_spent' => 1,
            'status' => 'new',
        ]);
    }

    private function premoderation(bool $on): void
    {
        Setting::updateOrCreate(
            ['key' => 'reviews_premoderation'],
            ['group' => 'moderation', 'label' => 'Премодерация', 'type' => 'boolean', 'value' => $on],
        );
    }

    private function leave(string $body): Review
    {
        $this->actingAs($this->buyer)->post("/company/{$this->supplier->slug}/review", [
            'rating' => 5,
            'body' => $body,
        ]);

        return Review::latest('id')->firstOrFail();
    }

    private const CLEAN = 'Отгрузили цемент в срок, документы прислали в тот же день. Работаем второй раз.';

    // ── Настройка ────────────────────────────────────────────

    #[Test]
    public function при_включённой_премодерации_отзыв_ждёт_проверки(): void
    {
        $this->premoderation(true);

        $review = $this->leave(self::CLEAN);

        $this->assertSame(Review::STATUS_MODERATION, $review->status);
        $this->assertNull($review->screening_flags, 'чистый текст отметок не получает');
    }

    #[Test]
    public function при_выключенной_премодерации_чистый_отзыв_публикуется(): void
    {
        $this->premoderation(false);

        $this->assertSame(Review::STATUS_PUBLISHED, $this->leave(self::CLEAN)->status);
    }

    /** По умолчанию проверка включена: настройки может не быть вовсе. */
    #[Test]
    public function без_настройки_премодерация_считается_включённой(): void
    {
        $this->assertSame(Review::STATUS_MODERATION, $this->leave(self::CLEAN)->status);
    }

    // ── Автоматический отбор ─────────────────────────────────

    /** @return list<array{string, string}> */
    public static function подозрительныеТексты(): array
    {
        return [
            'телефон' => ['Работают хорошо, звоните напрямую +998 90 123-45-67, договоримся дешевле', 'контакты'],
            'телефон без разделителей' => ['Нормальный поставщик, мой номер 998901234567 для связи по опту', 'контакты'],
            'почта' => ['Хороший поставщик, пишите на sales@example.com за прайсом на весь ассортимент', 'контакты'],
            'ссылка' => ['Всё отлично, подробности и цены смотрите на https://example.com/prices тут', 'контакты'],
            'телеграм' => ['Отличная компания, для заказов пишите @postavshik_uz в телеграме круглосуточно', 'контакты'],
            'брань' => ['Полная хуйня, а не поставка, сроки сорвали дважды и даже не предупредили', 'брань'],
            'крик' => ['УЖАСНЫЙ ПОСТАВЩИК НИКОМУ НЕ СОВЕТУЮ СРЫВАЮТ ВСЕ СРОКИ И НЕ ОТВЕЧАЮТ', 'заглавными'],
        ];
    }

    /**
     * Отбор работает и при выключенной премодерации: настройка
     * ускоряет публикацию хороших отзывов, а не открывает витрину
     * для чего угодно.
     */
    #[Test]
    #[DataProvider('подозрительныеТексты')]
    public function подозрительный_текст_уходит_модератору(string $body, string $expectedFlag): void
    {
        $this->premoderation(false);

        $review = $this->leave($body);

        $this->assertSame(Review::STATUS_MODERATION, $review->status);
        $this->assertStringContainsString($expectedFlag, mb_strtolower((string) $review->screening_flags));
    }

    /**
     * Цифры — не всегда телефон.
     *
     * Подробный отзыв со стандартами, объёмами и суммами — ровно то,
     * что площадке нужнее всего. Гонять его через модератора из-за
     * похожего на номер сочетания цифр значит наказывать за подробность.
     *
     * @return list<array{string}>
     */
    public static function текстыСЧислами(): array
    {
        return [
            'цена' => ['Взяли партию 500 тонн по цене 1 200 000 сум за тонну, отгрузили за 3 дня.'],
            'миллионы' => ['Договор №12/2026 от 15.03, объём 12 000 000 сум, выполнен полностью.'],
            'ГОСТ' => ['Партия арматуры А500С, 12 мм, 40 тонн. Качество по ГОСТ 34028-2016.'],
            'режим работы' => ['Работают с 2015 года, склад на 3000 м2, отгрузка с 8:00 до 18:00.'],
        ];
    }

    #[Test]
    #[DataProvider('текстыСЧислами')]
    public function числа_в_тексте_не_считаются_контактами(string $body): void
    {
        $this->premoderation(false);

        $this->assertSame(Review::STATUS_PUBLISHED, $this->leave($body)->status);
    }

    /** @return list<array{string}> */
    public static function записиТелефона(): array
    {
        return [
            'с плюсом' => ['Хорошие ребята, звоните +998 90 123-45-67, договоримся дешевле'],
            'подряд' => ['Нормальный поставщик, мой номер 998901234567 для связи по опту'],
            'группами' => ['Отличная компания, телефон 90 123 45 67, звоните после обеда'],
        ];
    }

    #[Test]
    #[DataProvider('записиТелефона')]
    public function телефон_узнаётся_в_любой_записи(string $body): void
    {
        $this->premoderation(false);

        $this->assertSame(Review::STATUS_MODERATION, $this->leave($body)->status);
    }

    /** Подстановка латиницы не должна обходить проверку на брань. */
    #[Test]
    public function подмена_букв_не_обходит_проверку(): void
    {
        $this->assertNotSame([], ReviewScreening::reasons('Полная пиздец работа, сроки сорваны'));
        $this->assertNotSame([], ReviewScreening::reasons('Ну и cyка же этот поставщик, сроки сорвал'));
    }

    // ── Что видит покупатель ─────────────────────────────────

    #[Test]
    public function отзыв_на_проверке_не_виден_на_витрине(): void
    {
        $this->premoderation(true);
        $this->leave(self::CLEAN);

        $this->get("/company/{$this->supplier->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page->has('reviews', 0));
    }

    #[Test]
    public function отзыв_на_проверке_не_попадает_в_рейтинг(): void
    {
        $this->premoderation(true);
        $this->leave(self::CLEAN);

        $this->assertSame(0, $this->supplier->fresh()->reviews_count);
        $this->assertSame(0.0, (float) $this->supplier->fresh()->rating);
    }

    /**
     * Компания не должна знать об отзыве, пока он не опубликован —
     * иначе она ответит на то, что может и не появиться.
     */
    #[Test]
    public function компания_не_узнаёт_об_отзыве_до_публикации(): void
    {
        $owner = User::factory()->for($this->supplier)->create();

        $this->premoderation(true);
        $this->leave(self::CLEAN);

        $this->assertSame(0, $owner->alerts()->where('type', 'review')->count());
    }

    /**
     * Автор своего отзыва на витрине не увидит — его там нет.
     * Без объяснения он читает «вы уже оставляли отзыв» и не понимает,
     * куда тот делся.
     */
    #[Test]
    public function визитка_объясняет_автору_где_его_отзыв(): void
    {
        $this->premoderation(true);
        $this->leave(self::CLEAN);

        $this->actingAs($this->buyer)
            ->get("/company/{$this->supplier->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('review_blocked', fn (?string $r): bool => $r !== null && str_contains($r, 'на проверке')),
            );
    }

    #[Test]
    public function автор_видит_что_отзыв_ушёл_на_проверку(): void
    {
        $this->premoderation(true);

        $this->actingAs($this->buyer)
            ->post("/company/{$this->supplier->slug}/review", ['rating' => 5, 'body' => self::CLEAN])
            ->assertSessionHas('success', fn (string $m): bool => str_contains($m, 'на проверку'));
    }

    /** Причина задержки называется прямо: догадываться человек не должен. */
    #[Test]
    public function автор_узнаёт_причину_задержки(): void
    {
        $this->premoderation(false);

        $this->actingAs($this->buyer)
            ->post("/company/{$this->supplier->slug}/review", [
                'rating' => 5,
                'body' => 'Хорошая компания, звоните +998 90 123-45-67 и договаривайтесь напрямую',
            ])
            ->assertSessionHas('success', fn (string $m): bool => str_contains($m, 'контакты'));
    }

    // ── Решение модератора ───────────────────────────────────

    private function moderator(): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_MODERATOR,
            'status' => 'active',
        ]);
    }

    #[Test]
    public function одобренный_отзыв_появляется_на_витрине(): void
    {
        $this->premoderation(true);
        $review = $this->leave(self::CLEAN);
        $owner = User::factory()->for($this->supplier)->create();

        $this->actingAs($this->moderator());

        Livewire::test(ListReviews::class)
            ->callAction(TestAction::make('approve')->table($review));

        $review->refresh();

        $this->assertSame(Review::STATUS_PUBLISHED, $review->status);
        $this->assertSame(1, $this->supplier->fresh()->reviews_count);

        // Уведомление уходит именно здесь, а не при создании
        $this->assertSame(1, $owner->alerts()->where('type', 'review')->count());
    }

    #[Test]
    public function отклонённый_отзыв_на_витрину_не_попадает(): void
    {
        $this->premoderation(true);
        $review = $this->leave(self::CLEAN);
        $author = User::factory()->for($this->buyerCompany)->create();

        $this->actingAs($this->moderator());

        Livewire::test(ListReviews::class)
            ->callAction(TestAction::make('rejectReview')->table($review), [
                'note' => 'В тексте указан телефон — контакты раскрываются платно',
            ]);

        $review->refresh();

        $this->assertSame(Review::STATUS_HIDDEN, $review->status);
        $this->assertSame(0, $this->supplier->fresh()->reviews_count);

        // Автор должен узнать причину: молча исчезнувший отзыв читается
        // как «площадка убирает неудобное»
        $this->assertSame(1, $author->alerts()->count());
    }

    #[Test]
    public function отклонение_требует_формулировки(): void
    {
        $this->premoderation(true);
        $review = $this->leave(self::CLEAN);

        $this->actingAs($this->moderator());

        Livewire::test(ListReviews::class)
            ->callAction(TestAction::make('rejectReview')->table($review), ['note' => 'нет'])
            ->assertHasActionErrors(['note']);

        $this->assertSame(Review::STATUS_MODERATION, $review->fresh()->status);
    }
}
