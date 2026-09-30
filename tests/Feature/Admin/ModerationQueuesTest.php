<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Company;
use App\Models\CompanyDocument;
use App\Models\ContactUnlock;
use App\Models\Review;
use App\Models\User;
use App\Models\Wallet;
use App\Services\ModerationService;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
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

        // Кнопка — в админке Django (python/savdex/finance); здесь — служба Laravel
        app(ModerationService::class)->acceptComplaint($unlock, $this->moderator, 'Контакт проверен, компания не отвечает — возвращаем');

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

        // Кнопка — в админке Django (python/savdex/finance); здесь — служба Laravel
        app(ModerationService::class)->acceptComplaint($unlock, $this->moderator, 'Контакт проверен, компания не отвечает — возвращаем');

        $wallet->refresh();

        $this->assertSame(2, $wallet->contacts_used_this_period);
        $this->assertSame(0, $wallet->credits, 'кредит за лимитный контакт начисляться не должен');
    }

    #[Test]
    public function отклонённая_жалоба_ничего_не_возвращает(): void
    {
        $unlock = $this->complaint();
        $wallet = Wallet::create(['company_id' => $unlock->company_id, 'credits' => 2]);

        app(ModerationService::class)->declineComplaint($unlock, $this->moderator, 'Контакт рабочий, дозвонились с первого раза');

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

    // ── Доступ ───────────────────────────────────────────────

    /** Модерация — работа модератора, разделы должны быть ему открыты. */
    #[Test]
    public function модератор_видит_все_три_очереди(): void
    {
        $this->assertTrue(AdminAccess::allows('reviews.edit'));
        $this->assertTrue(AdminAccess::allows('documents.moderate'));
        $this->assertTrue(AdminAccess::allows('complaints.view'));
    }
}
