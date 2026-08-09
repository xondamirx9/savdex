<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Broadcast;
use App\Models\Company;
use App\Models\User;
use App\Models\UserNotification;
use App\Support\Notifier;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\Support\DatabaseNotification;
use Tests\TestCase;

/**
 * Уведомления пользователя и рассылки администратора.
 *
 * До этой доработки колокольчик в шапке был декоративным: страницы
 * не существовало, счётчик всегда показывал ноль.
 */
class NotificationTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function страница_открывается_и_отдаёт_список(): void
    {
        $user = User::factory()->create();

        UserNotification::deliver($user, [
            'type' => 'new_review',
            'title' => 'Новый отзыв: 5 звёзд',
        ]);

        $this->actingAs($user)
            ->get('/notifications')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('Notifications')
                ->has('notifications', 1)
                ->where('unread', 1),
            );
    }

    #[Test]
    public function непрочитанные_фильтруются(): void
    {
        $user = User::factory()->create();

        UserNotification::deliver($user, ['type' => 'moderation', 'title' => 'Прочитанное', 'read_at' => now()]);
        UserNotification::deliver($user, ['type' => 'moderation', 'title' => 'Новое']);

        $this->actingAs($user)
            ->get('/notifications?filter=unread')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('notifications', 1)
                ->where('notifications.0.title', 'Новое'),
            );
    }

    #[Test]
    public function открытие_отмечает_прочитанным_и_ведёт_по_ссылке(): void
    {
        $user = User::factory()->create();

        $notification = UserNotification::deliver($user, [
            'type' => 'listing_expiring',
            'title' => 'Объявление истекает',
            'url' => '/cabinet/listings',
        ]);

        $this->actingAs($user)
            ->post("/notifications/{$notification->id}/read")
            ->assertRedirect('/cabinet/listings');

        $this->assertNotNull($notification->fresh()->read_at);
    }

    /**
     * Чужое уведомление не должно открываться по номеру.
     * Именно 404, а не 403: 403 подтверждает, что запись существует.
     */
    #[Test]
    public function чужое_уведомление_недоступно(): void
    {
        $owner = User::factory()->create();
        $stranger = User::factory()->create();

        $notification = UserNotification::deliver($owner, ['type' => 'moderation', 'title' => 'Чужое']);

        $this->actingAs($stranger)
            ->post("/notifications/{$notification->id}/read")
            ->assertNotFound();

        $this->assertNull($notification->fresh()->read_at);
    }

    #[Test]
    public function отметить_всё_прочитанным(): void
    {
        $user = User::factory()->create();

        UserNotification::deliver($user, ['type' => 'moderation', 'title' => 'Раз']);
        UserNotification::deliver($user, ['type' => 'moderation', 'title' => 'Два']);

        $this->actingAs($user)->post('/notifications/read-all');

        $this->assertSame(0, $user->alerts()->unread()->count());
    }

    #[Test]
    public function счётчик_приходит_в_общие_данные(): void
    {
        $user = User::factory()->create();

        UserNotification::deliver($user, ['type' => 'moderation', 'title' => 'Новое']);

        $this->actingAs($user)
            ->get('/cabinet')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('bell.unread', 1)
                ->has('bell.latest', 1),
            );
    }

    /**
     * Общий проп колокольчика и проп страницы не должны носить одно имя.
     *
     * Когда оба назывались notifications, проп страницы (список записей)
     * перекрывал общий (объект со счётчиком), шапка падала на latest.map
     * и страница уведомлений открывалась пустой — ошибка внутри React
     * рушит всё дерево, а не одну шапку.
     */
    #[Test]
    public function проп_страницы_не_перекрывает_данные_колокольчика(): void
    {
        $user = User::factory()->create();

        UserNotification::deliver($user, ['type' => 'moderation', 'title' => 'Новое']);

        $this->actingAs($user)
            ->get('/notifications')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('notifications', 1)
                ->has('bell.latest', 1)
                ->where('bell.unread', 1),
            );
    }

    /**
     * Штатный механизм уведомлений Laravel должен остаться рабочим.
     *
     * Когда наше отношение называлось notifications, оно перекрывало
     * отношение из трейта Notifiable, и $user->notify() падал с
     * MassAssignmentException — Filament именно так сообщает о готовой
     * выгрузке, и уведомление не доходило.
     */
    #[Test]
    public function штатные_уведомления_laravel_не_сломаны(): void
    {
        $user = User::factory()->create();

        $user->notify(new DatabaseNotification);

        $this->assertSame(1, $user->notifications()->count());
        // Наши уведомления живут отдельно и не смешиваются
        $this->assertSame(0, $user->alerts()->count());
    }

    /**
     * Событие компании порождает и запись в ленте, и уведомления
     * каждому сотруднику — иначе второй сотрудник о нём не узнает.
     */
    #[Test]
    public function событие_компании_уведомляет_всех_сотрудников(): void
    {
        $company = Company::factory()->create();
        $owner = User::factory()->create(['company_id' => $company->id]);
        $manager = User::factory()->create(['company_id' => $company->id]);

        app(Notifier::class)->company($company, 'new_review', 'Новый отзыв');

        $this->assertSame(1, $owner->alerts()->count());
        $this->assertSame(1, $manager->alerts()->count());
        $this->assertSame(1, $company->events()->count());
    }

    #[Test]
    public function рассылка_доходит_до_всех_активных(): void
    {
        User::factory()->count(3)->create(['status' => 'active']);
        User::factory()->create(['status' => 'blocked']);

        $broadcast = Broadcast::create([
            'title' => 'Плановые работы в воскресенье',
            'body' => 'С 02:00 до 04:00 площадка будет недоступна.',
            'audience' => 'all',
            'tone' => 'warning',
        ]);

        $sent = app(Notifier::class)->broadcast($broadcast);

        $this->assertSame(3, $sent, 'Заблокированным рассылка идти не должна');
        $this->assertSame(3, $broadcast->fresh()->recipients_count);
        $this->assertNotNull($broadcast->fresh()->sent_at);
        $this->assertSame(3, UserNotification::where('is_broadcast', true)->count());
    }

    #[Test]
    public function рассылка_по_сегменту_без_компании(): void
    {
        $company = Company::factory()->create();
        User::factory()->create(['company_id' => $company->id, 'status' => 'active']);
        User::factory()->count(2)->create(['company_id' => null, 'status' => 'active']);

        $broadcast = Broadcast::create([
            'title' => 'Заполните данные компании',
            'body' => 'Без карточки компании объявления публиковать нельзя.',
            'audience' => 'no_company',
        ]);

        $this->assertSame(2, app(Notifier::class)->broadcast($broadcast));
    }
}
