<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Widgets\ModerationQueue;
use App\Jobs\TranslateListing;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Queue;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Публикация загруженного объявления.
 *
 * Загрузка из книги кладёт объявления в «На проверке» — на витрину
 * они попадают только кнопкой «Одобрить». Сами решения модератора
 * («Одобрить», «Вернуть на исправление», «Отклонить») — в разделе
 * «Объявления» на Python (python/tests/test_listings_admin.py). Здесь —
 * пункт меню и очередь на панели, которые туда ведут, и то, что от
 * админки не зависит.
 */
class ListingApprovalTest extends TestCase
{
    use RefreshDatabase;

    private const LINK = '/admin/python?next=/py/admin/data/listing/';

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    private function pending(): Listing
    {
        return Listing::factory()->for(Company::factory())->create([
            'status' => Listing::STATUS_MODERATION,
            'source' => Listing::SOURCE_IMPORT,
            'published_at' => null,
            'expires_at' => null,
        ]);
    }

    /** Счётчик у пункта меню — очередь модерации: сюда заходят именно за ней. */
    #[Test]
    public function пункт_меню_считает_очередь_на_проверку(): void
    {
        $this->pending();
        $this->pending();
        Listing::factory()->for(Company::factory())->create(['status' => Listing::STATUS_ACTIVE]);

        $html = $this->actingAs($this->admin(AdminAccess::MODERATOR))->get('/admin')->getContent();
        $at = strpos($html, 'href="'.self::LINK.'"');

        $this->assertNotFalse($at, 'пункт «Объявления» ведёт в раздел на Python');

        $item = substr($html, $at, 3000);

        $this->assertMatchesRegularExpression('/>\s*2\s*</', $item, 'в значке — два объявления на проверке');

        // Финансам раздел не положен — и пункта нет
        $this->actingAs($this->admin(AdminAccess::FINANCE))
            ->get('/admin')
            ->assertDontSee(self::LINK, false);
    }

    /** Плашка «Объявления» на панели модератора ведёт сразу в очередь. */
    #[Test]
    public function очередь_на_панели_ведёт_в_раздел_с_фильтром(): void
    {
        $this->pending();

        Livewire::actingAs($this->admin(AdminAccess::MODERATOR))
            ->test(ModerationQueue::class)
            ->assertSeeHtml(e(self::LINK.urlencode('?status=moderation')));
    }

    /**
     * Книга дала английский, остальных языков нет: публикация должна
     * позвать машинный перевод за недостающими, а не считать, что раз
     * переводы «есть», добирать нечего.
     */
    #[Test]
    public function публикация_с_частью_языков_запускает_добор_перевода(): void
    {
        config()->set('services.machine_translation.enabled', true);
        Queue::fake();

        $listing = $this->pending();
        $listing->forceFill(['title_i18n' => ['en' => 'Ceramic brick M150']])->save();

        Queue::assertNothingPushed();

        $listing->forceFill(['status' => Listing::STATUS_ACTIVE, 'published_at' => now()])->save();

        Queue::assertPushed(TranslateListing::class, fn (TranslateListing $job): bool => $job->listingId === $listing->id);
    }

    #[Test]
    public function непроверенное_на_витрине_не_показывается(): void
    {
        $listing = $this->pending();

        $this->get('/listing/'.$listing->slug)->assertNotFound();
        $this->get('/catalog')->assertOk()->assertDontSee($listing->title);
    }
}
