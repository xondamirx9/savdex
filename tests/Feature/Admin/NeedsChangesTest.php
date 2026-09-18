<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

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
}
