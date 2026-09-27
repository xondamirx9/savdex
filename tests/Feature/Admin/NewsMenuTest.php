<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Widgets\ContentDrafts;
use App\Models\NewsPost;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Новости в меню и на главной админки.
 *
 * Раздел с этапа 2 переноса работает на Python
 * (python/savdex/site/admin.py, проверки — python/tests/test_news_admin.py).
 * Здесь — пункт меню и то, что плашки «Черновики» и «Выйдут по
 * расписанию» ведут в него с нужным фильтром, а не в пустоту.
 */
class NewsMenuTest extends TestCase
{
    use RefreshDatabase;

    private const LINK = '/admin/python?next=/py/admin/site/newspost/';

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true, 'admin_role' => $role, 'status' => 'active',
        ]);
    }

    #[Test]
    public function пункт_новостей_видят_те_же_кто_правит_контент(): void
    {
        foreach ([AdminAccess::SUPERADMIN, AdminAccess::ADMIN, AdminAccess::CONTENT_MANAGER] as $role) {
            $this->actingAs($this->admin($role));
            $this->get('/admin')->assertSee(self::LINK, false);
        }

        foreach ([AdminAccess::SALES, AdminAccess::FINANCE, AdminAccess::SUPPORT] as $role) {
            $this->actingAs($this->admin($role));
            $this->get('/admin')->assertDontSee(self::LINK, false);
        }
    }

    #[Test]
    public function плашки_ведут_в_раздел_с_фильтром(): void
    {
        NewsPost::query()->create([
            'slug' => 'chernovik', 'category' => 'Полезное', 'title' => 'Черновик',
            'excerpt' => 'Коротко', 'body' => 'Текст', 'is_published' => false,
        ]);

        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));

        // Плашки на главной админки подгружаются отдельно — проверяем сам виджет
        Livewire::test(ContentDrafts::class)
            ->assertSeeHtml(e(self::LINK.urlencode('?status=draft')))
            ->assertSeeHtml(e(self::LINK.urlencode('?status=scheduled')));
    }
}
