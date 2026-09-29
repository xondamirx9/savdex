<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Resume;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Модерация резюме.
 *
 * Публикация мгновенная, очереди на проверку нет: человек, который
 * ищет работу, не должен ждать сутки. Модератор приходит по жалобе
 * или просматривает свежие — и снимает то, чему в разделе не место,
 * обязательно с причиной: её видит соискатель у себя в кабинете.
 */
class ResumeModerationTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role = AdminAccess::MODERATOR): User
    {
        return User::factory()->create(['is_admin' => true, 'admin_role' => $role, 'status' => 'active']);
    }

    private function resume(): Resume
    {
        $resume = new Resume(['title' => 'Менеджер по снабжению', 'contact_name' => 'Максуд Максудов']);
        $resume->user_id = User::factory()->create()->id;
        $resume->status = Resume::STATUS_PUBLISHED;
        $resume->published_at = now();
        $resume->save();
        $resume->slug = Resume::makeSlug($resume->title, $resume->id);
        $resume->saveQuietly();

        return $resume;
    }

    /** Снятое модерацией соискатель обратно не опубликует. */
    #[Test]
    public function снятое_модерацией_видно_в_кабинете_с_причиной(): void
    {
        $resume = $this->resume();
        $resume->forceFill([
            'status' => Resume::STATUS_BLOCKED,
            'moderation_note' => 'Вместо резюме реклама.',
        ])->save();

        $this->actingAs(User::find($resume->user_id))
            ->get('/cabinet/resume')
            ->assertInertia(fn ($page) => $page
                ->where('resume.status', Resume::STATUS_BLOCKED)
                ->where('resume.moderation_note', 'Вместо резюме реклама.'));
    }

    #[Test]
    public function снятое_резюме_пропадает_из_раздела(): void
    {
        $resume = $this->resume();

        $this->get('/resumes')->assertInertia(fn ($page) => $page->where('total', 1));

        $resume->forceFill(['status' => Resume::STATUS_BLOCKED, 'moderation_note' => 'Реклама'])->save();

        $this->get('/resumes')->assertInertia(fn ($page) => $page->where('total', 0));
        $this->get('/resume/'.$resume->slug)->assertNotFound();
    }
}
