<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Pages\Complaints;
use App\Filament\Resources\CompanyDocuments\CompanyDocumentResource;
use App\Filament\Resources\CompanyDocuments\Pages\ListCompanyDocuments;
use App\Filament\Resources\Reviews\Pages\ListReviews;
use App\Filament\Resources\Reviews\ReviewResource;
use App\Models\Company;
use App\Models\CompanyDocument;
use App\Models\ContactUnlock;
use App\Models\Review;
use App\Models\User;
use App\Models\Wallet;
use App\Services\ModerationService;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Очереди модерации: споры по отзывам, жалобы на контакты, документы.
 *
 * Все три обращения раньше упирались в тупик — статус ставился
 * в «pending», и экрана, где его увидит модератор, не существовало.
 * По жалобам на контакты это к тому же невыполненное обещание
 * в деньгах: «вернём кредит, если контакт нерабочий».
 */
class ModerationQueuesTest extends TestCase
{
    use RefreshDatabase;

    private User $moderator;

    protected function setUp(): void
    {
        parent::setUp();

        $this->moderator = User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_MODERATOR,
            'status' => 'active',
            'name' => 'Модератор Пулатов',
        ]);

        $this->actingAs($this->moderator);
    }

    // ── Споры по отзывам ─────────────────────────────────────

    private function disputed(int $rating = 1): Review
    {
        return Review::factory()->create([
            'rating' => $rating,
            'status' => 'published',
            'dispute_status' => 'pending',
            'dispute_reason' => 'Компания у нас ничего не заказывала, отзыв от конкурента',
        ]);
    }

    #[Test]
    public function удовлетворённый_спор_скрывает_отзыв_и_пересчитывает_рейтинг(): void
    {
        $review = $this->disputed();
        $company = $review->company;

        Review::factory()->count(3)->create(['company_id' => $company->id, 'rating' => 5]);

        Livewire::test(ListReviews::class)
            ->callAction(TestAction::make('acceptDispute')->table($review), [
                'note' => 'Сделка не подтверждена ни одной из сторон',
            ]);

        $review->refresh();

        $this->assertSame('hidden', $review->status);
        $this->assertSame('accepted', $review->dispute_status);
        $this->assertSame($this->moderator->id, $review->moderated_by);
        $this->assertNotNull($review->moderated_at);

        // Скрытый отзыв больше не тянет оценку вниз
        $this->assertSame(3, $company->fresh()->reviews_count);
    }

    /** Решение уходит обеим сторонам: и компании, и автору отзыва. */
    #[Test]
    public function о_решении_узнают_обе_стороны(): void
    {
        $review = $this->disputed();

        $owner = User::factory()->for($review->company)->create();
        $author = User::factory()->for($review->authorCompany)->create();

        Livewire::test(ListReviews::class)
            ->callAction(TestAction::make('acceptDispute')->table($review), [
                'note' => 'Сделка не подтверждена ни одной из сторон',
            ]);

        $this->assertSame(1, $owner->alerts()->count(), 'компания должна узнать о решении');
        $this->assertSame(1, $author->alerts()->count(), 'автор отзыва тоже — иначе он узнает случайно');
    }

    #[Test]
    public function отклонённый_спор_оставляет_отзыв_на_витрине(): void
    {
        $review = $this->disputed();

        Livewire::test(ListReviews::class)
            ->callAction(TestAction::make('declineDispute')->table($review), [
                'note' => 'Раскрытие контактов и переписка подтверждены',
            ]);

        $review->refresh();

        $this->assertSame('published', $review->status);
        $this->assertSame('declined', $review->dispute_status);
    }

    /**
     * Решение бывает ошибочным — скрытый отзыв возвращается.
     *
     * Фильтр очереди снимается: по умолчанию список показывает только
     * нерешённые споры, а уже решённый в него не попадает — за откатом
     * модератор идёт в общий список.
     */
    #[Test]
    public function скрытый_отзыв_возвращается_на_витрину(): void
    {
        $review = Review::factory()->create(['status' => 'hidden', 'dispute_status' => 'accepted']);

        Livewire::test(ListReviews::class)
            ->removeTableFilter('needs_action')
            ->callAction(TestAction::make('restore')->table($review));

        $this->assertSame('published', $review->fresh()->status);
        $this->assertSame(1, $review->company->fresh()->reviews_count);
    }

    #[Test]
    public function решение_требует_формулировки(): void
    {
        $review = $this->disputed();

        Livewire::test(ListReviews::class)
            ->callAction(TestAction::make('acceptDispute')->table($review), ['note' => 'нет'])
            ->assertHasActionErrors(['note']);

        $this->assertSame('published', $review->fresh()->status);
    }

    // ── Жалобы на контакты ───────────────────────────────────

    /** @param array<string, mixed> $overrides */
    private function complaint(array $overrides = []): ContactUnlock
    {
        return ContactUnlock::factory()->create([
            'complaint_status' => 'pending',
            'complaint_reason' => 'Телефон не отвечает третью неделю, почта отбивается',
            'credits_spent' => 1,
            'refunded' => false,
            ...$overrides,
        ]);
    }

    #[Test]
    public function обоснованная_жалоба_возвращает_кредит(): void
    {
        $unlock = $this->complaint();
        $wallet = Wallet::create(['company_id' => $unlock->company_id, 'credits' => 2]);

        Livewire::test(Complaints::class)
            ->callAction(TestAction::make('accept')->table($unlock), [
                'note' => 'Контакт проверен, компания не отвечает — возвращаем',
            ]);

        $unlock->refresh();

        $this->assertSame('accepted', $unlock->complaint_status);
        $this->assertTrue($unlock->refunded);
        $this->assertSame(3, $wallet->fresh()->credits, 'кредит должен вернуться на счёт');

        $this->assertDatabaseHas('wallet_transactions', [
            'company_id' => $unlock->company_id,
            'amount' => 1,
            'reason' => 'complaint_refund',
        ]);
    }

    /**
     * Контакт, оплаченный лимитом тарифа, возвращается в лимит.
     * Начислять за него кредит значит выдавать больше, чем списали.
     */
    #[Test]
    public function контакт_из_лимита_возвращается_в_лимит(): void
    {
        $unlock = $this->complaint(['credits_spent' => 0]);
        $wallet = Wallet::create([
            'company_id' => $unlock->company_id,
            'credits' => 0,
            'contacts_used_this_period' => 3,
        ]);

        Livewire::test(Complaints::class)
            ->callAction(TestAction::make('accept')->table($unlock), [
                'note' => 'Контакт проверен, компания не отвечает — возвращаем',
            ]);

        $wallet->refresh();

        $this->assertSame(2, $wallet->contacts_used_this_period);
        $this->assertSame(0, $wallet->credits, 'кредит за лимитный контакт начисляться не должен');
    }

    #[Test]
    public function отклонённая_жалоба_ничего_не_возвращает(): void
    {
        $unlock = $this->complaint();
        $wallet = Wallet::create(['company_id' => $unlock->company_id, 'credits' => 2]);

        Livewire::test(Complaints::class)
            ->callAction(TestAction::make('decline')->table($unlock), [
                'note' => 'Контакт рабочий, дозвонились с первого раза',
            ]);

        $this->assertSame('declined', $unlock->fresh()->complaint_status);
        $this->assertFalse($unlock->fresh()->refunded);
        $this->assertSame(2, $wallet->fresh()->credits);
    }

    /** Повторное решение не должно возвращать кредит дважды. */
    #[Test]
    public function повторный_возврат_не_начисляется(): void
    {
        $unlock = $this->complaint(['refunded' => true, 'complaint_status' => 'accepted']);
        $wallet = Wallet::create(['company_id' => $unlock->company_id, 'credits' => 5]);

        app(ModerationService::class)
            ->acceptComplaint($unlock, $this->moderator, 'Повторное решение по той же жалобе');

        $this->assertSame(5, $wallet->fresh()->credits);
    }

    // ── Документы ────────────────────────────────────────────

    private function document(string $type = 'license'): CompanyDocument
    {
        return CompanyDocument::create([
            'company_id' => Company::factory()->create()->id,
            'type' => $type,
            'title' => 'Лицензия на строительные работы',
            'file_path' => 'companies/1/documents/test.pdf',
            'file_size' => 102400,
            'mime' => 'application/pdf',
            'is_public' => true,
            'moderation_status' => CompanyDocument::STATUS_PENDING,
        ]);
    }

    #[Test]
    public function принятый_документ_появляется_на_визитке(): void
    {
        $document = $this->document();

        $this->assertFalse($document->isVisibleOnCard(), 'до проверки документ на визитке не показывается');

        Livewire::test(ListCompanyDocuments::class)
            ->callAction(TestAction::make('approve')->table($document));

        $document->refresh();

        $this->assertSame(CompanyDocument::STATUS_APPROVED, $document->moderation_status);
        $this->assertTrue($document->isVisibleOnCard());
        $this->assertSame($this->moderator->id, $document->moderated_by);
    }

    /**
     * Одобрение документа не выдаёт бейдж «Проверена»: он вручается
     * отдельным решением по совокупности, иначе его давала бы загрузка файла.
     */
    #[Test]
    public function одобрение_документа_не_поднимает_уровень_проверки(): void
    {
        $document = $this->document();
        $level = $document->company->verification_level;

        Livewire::test(ListCompanyDocuments::class)
            ->callAction(TestAction::make('approve')->table($document));

        $this->assertSame($level, $document->company->fresh()->verification_level);
    }

    #[Test]
    public function отклонение_документа_требует_причины(): void
    {
        $document = $this->document();

        Livewire::test(ListCompanyDocuments::class)
            ->callAction(TestAction::make('reject')->table($document), ['reason' => 'плохо'])
            ->assertHasActionErrors(['reason']);

        $this->assertSame(CompanyDocument::STATUS_PENDING, $document->fresh()->moderation_status);
    }

    #[Test]
    public function отклонённый_документ_объясняет_причину_компании(): void
    {
        $document = $this->document();
        $owner = User::factory()->for($document->company)->create();

        Livewire::test(ListCompanyDocuments::class)
            ->callAction(TestAction::make('reject')->table($document), [
                'reason' => 'Скан нечитаемый: печать и номер лицензии не видны',
            ]);

        $document->refresh();

        $this->assertSame(CompanyDocument::STATUS_REJECTED, $document->moderation_status);
        $this->assertStringContainsString('нечитаемый', $document->moderation_note);
        $this->assertSame(1, $owner->alerts()->count());
    }

    /** Материалы модерации не подлежат и в очередь не попадают. */
    #[Test]
    public function презентации_в_очередь_не_попадают(): void
    {
        $material = CompanyDocument::create([
            'company_id' => Company::factory()->create()->id,
            'type' => 'presentation',
            'title' => 'Презентация компании',
            'file_path' => 'companies/1/documents/deck.pdf',
            'is_public' => true,
            'moderation_status' => CompanyDocument::STATUS_APPROVED,
        ]);

        Livewire::test(ListCompanyDocuments::class)->assertCanNotSeeTableRecords([$material]);
    }

    // ── Доступ ───────────────────────────────────────────────

    /** Модерация — работа модератора, разделы должны быть ему открыты. */
    #[Test]
    public function модератор_видит_все_три_очереди(): void
    {
        $this->assertTrue(ReviewResource::canViewAny());
        $this->assertTrue(CompanyDocumentResource::canViewAny());
        $this->assertTrue(Complaints::canAccess());
    }

    /**
     * Страницы открываются с данными.
     *
     * Права и действия проверяются выше по отдельности, но между
     * рабочим действием и открывающейся страницей есть зазор: битая
     * колонка или связь без with() роняет список целиком.
     */
    #[Test]
    public function страницы_очередей_открываются(): void
    {
        $this->disputed();
        $this->complaint();
        $this->document();

        foreach (['/admin/reviews', '/admin/complaints', '/admin/company-documents'] as $url) {
            $this->get($url)->assertSuccessful();
        }
    }

    /** Счётчики в меню считают именно нерешённое. */
    #[Test]
    public function счётчики_в_меню_показывают_очередь(): void
    {
        $this->assertNull(ReviewResource::getNavigationBadge(), 'пустая очередь счётчик не рисует');

        $this->disputed();
        $this->complaint();
        $this->document();

        $this->assertSame('1', ReviewResource::getNavigationBadge());
        $this->assertSame('1', Complaints::getNavigationBadge());
        $this->assertSame('1', CompanyDocumentResource::getNavigationBadge());
    }
}
