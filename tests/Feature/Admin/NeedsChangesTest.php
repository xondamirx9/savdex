<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Exceptions\RejectedListingStaysDown;
use App\Filament\Resources\Listings\Pages\ListListings;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * «Вернуть на исправление» — отдельный исход, а не мягкий отказ (§5.7 ТЗ).
 *
 * До этого статус был один. Опечатка в цене и спам получали одинаковый
 * ответ, а автор в обоих случаях жал «опубликовать заново» — и снятое
 * модератором объявление возвращалось на витрину неизменным. Решение
 * модератора не значило ничего.
 */
class NeedsChangesTest extends TestCase
{
    use RefreshDatabase;

    private function moderator(): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => AdminAccess::MODERATOR,
            'status' => 'active',
        ]);
    }

    private function listing(string $status = Listing::STATUS_ACTIVE): Listing
    {
        return Listing::factory()->create([
            'company_id' => Company::factory()->create()->id,
            'status' => $status,
        ]);
    }

    // ── Решение модератора ──────────────────────────────────────────

    #[Test]
    public function модератор_возвращает_объявление_с_замечанием(): void
    {
        $this->actingAs($this->moderator());
        $listing = $this->listing();

        Livewire::test(ListListings::class)
            ->callAction(TestAction::make('returnForChanges')->table($listing), ['reason' => 'В цене лишний ноль, поправьте.'])
            ->assertHasNoActionErrors();

        $listing->refresh();

        $this->assertSame(Listing::STATUS_NEEDS_CHANGES, $listing->status);
        $this->assertSame('В цене лишний ноль, поправьте.', $listing->moderation_note);
    }

    /**
     * Приёмка ТЗ, пункт 19: возврат без комментария не проходит.
     *
     * Отказ без причины возвращается в поддержку вопросом «а почему»,
     * и отвечать на него будет уже не модератор.
     */
    #[Test]
    public function возврат_без_комментария_не_проходит(): void
    {
        $this->actingAs($this->moderator());
        $listing = $this->listing();

        Livewire::test(ListListings::class)
            ->callAction(TestAction::make('returnForChanges')->table($listing), ['reason' => ''])
            ->assertHasActionErrors(['reason']);

        $this->assertSame(Listing::STATUS_ACTIVE, $listing->fresh()->status);
    }

    /** Отписка в два слова — тоже не объяснение. */
    #[Test]
    public function слишком_короткий_комментарий_не_проходит(): void
    {
        $this->actingAs($this->moderator());
        $listing = $this->listing();

        Livewire::test(ListListings::class)
            ->callAction(TestAction::make('returnForChanges')->table($listing), ['reason' => 'нет'])
            ->assertHasActionErrors(['reason']);
    }

    /** Отклонение осталось отдельным решением и тоже требует причины. */
    #[Test]
    public function отклонение_осталось_отдельным_решением(): void
    {
        $this->actingAs($this->moderator());
        $listing = $this->listing();

        Livewire::test(ListListings::class)
            ->callAction(TestAction::make('reject')->table($listing), ['reason' => 'Запрещённый товар, публикации не подлежит.'])
            ->assertHasNoActionErrors();

        $this->assertSame(Listing::STATUS_REJECTED, $listing->fresh()->status);
    }

    /** Возвращённое объявление уходит с витрины — иначе возврат ничего не меняет. */
    #[Test]
    public function возвращённое_объявление_не_видно_на_витрине(): void
    {
        $listing = $this->listing(Listing::STATUS_NEEDS_CHANGES);

        $this->assertFalse(
            Listing::query()->active()->whereKey($listing->id)->exists(),
            'объявление на исправлении не должно оставаться на витрине',
        );
    }

    // ── Сторона автора ──────────────────────────────────────────────

    private function author(Listing $listing): User
    {
        return User::factory()->create([
            'company_id' => $listing->company_id,
            'status' => 'active',
        ]);
    }

    #[Test]
    public function автор_правит_возвращённое_и_публикует_снова(): void
    {
        $listing = $this->listing(Listing::STATUS_NEEDS_CHANGES);
        $listing->forceFill(['moderation_note' => 'В цене лишний ноль.'])->save();

        $this->actingAs($this->author($listing))
            ->post("/cabinet/listings/{$listing->id}/resubmit")
            ->assertRedirect();

        $listing->refresh();

        $this->assertSame(Listing::STATUS_ACTIVE, $listing->status);
        $this->assertNull($listing->moderation_note, 'замечание снимается вместе с исправлением');
    }

    /**
     * Главное в этой правке: отклонённое обратно не возвращается.
     *
     * Раньше «опубликовать заново» работало и здесь — модератор снимал
     * объявление, автор возвращал его одним нажатием, и так по кругу.
     */
    #[Test]
    public function отклонённое_обратно_не_возвращается(): void
    {
        $listing = $this->listing(Listing::STATUS_REJECTED);
        $listing->forceFill(['moderation_note' => 'Запрещённый товар.'])->save();

        $this->actingAs($this->author($listing))
            ->post("/cabinet/listings/{$listing->id}/resubmit")
            ->assertRedirect();

        $this->assertSame(
            Listing::STATUS_REJECTED,
            $listing->fresh()->status,
            'отклонённое объявление на витрину не возвращается',
        );
    }

    /** Чужое объявление не вернуть даже зная номер. */
    #[Test]
    public function чужое_объявление_вернуть_нельзя(): void
    {
        $listing = $this->listing(Listing::STATUS_NEEDS_CHANGES);

        $stranger = User::factory()->create([
            'company_id' => Company::factory()->create()->id,
            'status' => 'active',
        ]);

        $this->actingAs($stranger)
            ->post("/cabinet/listings/{$listing->id}/resubmit")
            ->assertNotFound();

        $this->assertSame(Listing::STATUS_NEEDS_CHANGES, $listing->fresh()->status);
    }

    /** Вкладка «На исправлении» показывает именно возвращённые. */
    #[Test]
    public function вкладка_показывает_возвращённые(): void
    {
        $listing = $this->listing(Listing::STATUS_NEEDS_CHANGES);
        $this->listing(Listing::STATUS_ACTIVE)->forceFill(['company_id' => $listing->company_id])->save();

        $this->actingAs($this->author($listing))
            ->get('/cabinet/listings?status=needs_changes')
            ->assertOk()
            ->assertSee('needs_changes');
    }

    // ── Все пути в статус «активно» ─────────────────────────────────

    /**
     * Путей в статус «активно» четыре, и запрет должен стоять на всех.
     *
     * Проверка только в повторной публикации закрывала один путь
     * и оставляла три: продление, массовое продление и мастер.
     * Каждый из них возвращал снятое модератором объявление
     * на витрину неизменным.
     *
     * Проверяются все четыре сразу и называются все дырявые: падение
     * на первом же скрыло бы состояние остальных трёх, а именно это
     * и увело проверку в прошлый раз.
     */
    #[Test]
    public function отклонённое_не_возвращается_ни_одним_из_четырёх_путей(): void
    {
        $leaked = [];

        $attempts = [
            'повторная публикация' => fn (Listing $l) => $this->post("/cabinet/listings/{$l->id}/resubmit"),
            'продление' => fn (Listing $l) => $this->post("/cabinet/listings/{$l->id}/renew"),
            'мастер' => fn (Listing $l) => $this->post("/cabinet/listings/{$l->id}/publish", [
                'category_id' => $l->category_id,
                'title' => 'Заголовок достаточной длины для проверки',
                'description' => str_repeat('Описание объявления. ', 5),
                'price' => 1000,
            ]),
            'массовое продление' => fn (Listing $l) => $this->post('/cabinet/listings/bulk', [
                'action' => 'renew',
                'ids' => [$l->id],
            ]),
        ];

        foreach ($attempts as $name => $attempt) {
            $listing = $this->listing(Listing::STATUS_REJECTED);

            $this->actingAs($this->author($listing));

            try {
                $attempt($listing);
            } catch (\Throwable) {
                // Исключение — тоже отказ, и он засчитывается
            }

            if ($listing->fresh()->status === Listing::STATUS_ACTIVE) {
                $leaked[] = $name;
            }
        }

        $this->assertSame([], $leaked, 'отклонённое объявление вернулось на витрину через: '.implode(', ', $leaked));
    }

    /**
     * Запрет стоит в модели, а не только в контроллерах: путь, которого
     * ещё нет, тоже должен упереться.
     */
    #[Test]
    public function модель_не_даёт_поднять_отклонённое_даже_напрямую(): void
    {
        $listing = $this->listing(Listing::STATUS_REJECTED);

        $this->actingAs($this->author($listing));

        $this->expectException(RejectedListingStaysDown::class);

        $listing->forceFill(['status' => Listing::STATUS_ACTIVE])->save();
    }

    /**
     * Модератора запрет не касается: промах кнопкой исправлять некому,
     * если и ему закрыть путь назад.
     */
    #[Test]
    public function модератор_отменяет_своё_отклонение(): void
    {
        $this->actingAs($this->moderator());
        $listing = $this->listing(Listing::STATUS_REJECTED);

        Livewire::test(ListListings::class)
            ->callAction(TestAction::make('approve')->table($listing))
            ->assertHasNoActionErrors();

        $this->assertSame(Listing::STATUS_ACTIVE, $listing->fresh()->status);
    }

    /** Или возвращает автору на исправление — если дело поправимо. */
    #[Test]
    public function модератор_переводит_отклонённое_в_исправление(): void
    {
        $this->actingAs($this->moderator());
        $listing = $this->listing(Listing::STATUS_REJECTED);

        Livewire::test(ListListings::class)
            ->callAction(TestAction::make('returnForChanges')->table($listing), ['reason' => 'Поправьте цену и верните.'])
            ->assertHasNoActionErrors();

        $this->assertSame(Listing::STATUS_NEEDS_CHANGES, $listing->fresh()->status);
    }

    /**
     * Приёмка ТЗ, пункт 20: решение появилось в журнале с автором.
     *
     * Разграничение, которое нельзя проверить постфактум, — это
     * договорённость, а не защита.
     */
    #[Test]
    public function возврат_попадает_в_журнал_действий(): void
    {
        $moderator = $this->moderator();
        $this->actingAs($moderator);
        $listing = $this->listing();

        Livewire::test(ListListings::class)
            ->callAction(TestAction::make('returnForChanges')->table($listing), ['reason' => 'В цене лишний ноль, поправьте.'])
            ->assertHasNoActionErrors();

        $this->assertDatabaseHas('admin_actions', [
            'user_id' => $moderator->id,
            'section' => 'listings',
            'subject_id' => $listing->id,
        ]);
    }
}
