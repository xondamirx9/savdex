<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Banners\BannerResource;
use App\Filament\Resources\Banners\Pages\CreateBanner;
use App\Filament\Resources\Banners\Pages\ListBanners;
use App\Models\Banner;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Раздел баннеров в админке.
 *
 * Смысл раздела — завести акцию без разработчика. Поэтому проверяется
 * не «экран открылся», а «баннер создан через форму и виден».
 */
class BannerAdminTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        // Картинки кладутся на публичный диск: в тестах он поддельный,
        // иначе проверка засоряла бы настоящее хранилище
        Storage::fake('public');
    }

    /** Настоящая загрузка, а не строка пути: так проверяется и сам путь сохранения. */
    private function upload(string $name = 'banner.jpg'): UploadedFile
    {
        return UploadedFile::fake()->image($name, 2400, 800);
    }

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    private function banner(array $attrs = []): Banner
    {
        return Banner::query()->create(array_merge([
            'name' => 'Осенняя акция',
            'placement' => Banner::PLACEMENT_HOME,
            'alt' => 'Скидка 30%',
            'image_path' => 'banners/autumn.webp',
        ], $attrs));
    }

    // ── Доступ ──────────────────────────────────────────────────────

    /** Баннеры — тот же content, что страницы и новости (§4 ТЗ). */
    #[Test]
    public function баннеры_правят_те_же_кто_правит_контент(): void
    {
        foreach ([AdminAccess::SUPERADMIN, AdminAccess::ADMIN, AdminAccess::CONTENT_MANAGER] as $role) {
            $this->actingAs($this->admin($role));

            $this->assertTrue(BannerResource::canViewAny(), "{$role} должен видеть баннеры");
            $this->assertTrue(BannerResource::canCreate(), "{$role} должен заводить баннеры");
        }
    }

    #[Test]
    public function остальные_роли_баннеров_не_видят(): void
    {
        foreach ([AdminAccess::SALES, AdminAccess::FINANCE, AdminAccess::MODERATOR, AdminAccess::SUPPORT] as $role) {
            $this->actingAs($this->admin($role));

            $this->assertFalse(BannerResource::canViewAny(), "{$role} не должен видеть баннеры");
        }
    }

    // ── Экраны ──────────────────────────────────────────────────────

    #[Test]
    public function список_открывается_с_данными(): void
    {
        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));
        $banner = $this->banner();

        Livewire::test(ListBanners::class)
            ->assertOk()
            ->assertCanSeeTableRecords([$banner]);
    }

    /** Ради этого всё и делалось: акция заводится формой, без деплоя. */
    #[Test]
    public function баннер_заводится_через_форму(): void
    {
        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));

        Livewire::test(CreateBanner::class)
            ->fillForm([
                'name' => 'Октябрьская акция',
                'placement' => Banner::PLACEMENT_HOME,
                'alt' => 'Скидка 30% на годовой тариф до 30 октября',
                'url' => 'https://savdex.uz/pricing',
                'image_path' => [$this->upload('october.jpg')],
                'starts_at' => '2026-10-01 00:00',
                'ends_at' => '2026-10-30 23:59',
                'sort' => 0,
                'is_active' => true,
                'is_dismissible' => true,
                'focal_x' => 50,
                'focal_y' => 50,
            ])
            ->call('create')
            ->assertHasNoFormErrors();

        $banner = Banner::query()->where('name', 'Октябрьская акция')->first();

        $this->assertNotNull($banner);
        $this->assertSame(Banner::PLACEMENT_HOME, $banner->placement);
        $this->assertTrue($banner->isLive(Carbon::parse('2026-10-15 12:00')));
        $this->assertFalse($banner->isLive(Carbon::parse('2026-11-01 12:00')), 'после срока висеть не должен');
    }

    /** Конец раньше начала — акция, которой не будет. */
    #[Test]
    public function конец_раньше_начала_не_проходит(): void
    {
        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));

        Livewire::test(CreateBanner::class)
            ->fillForm([
                'name' => 'Ошибка в датах',
                'placement' => Banner::PLACEMENT_HOME,
                'alt' => 'Что-то',
                'image_path' => [$this->upload()],
                'starts_at' => '2026-10-30 00:00',
                'ends_at' => '2026-10-01 00:00',
                'sort' => 0,
            ])
            ->call('create')
            ->assertHasFormErrors(['ends_at']);
    }

    /** Подпись обязательна: баннер без неё для читалки экрана — пустое место. */
    #[Test]
    public function баннер_без_подписи_не_заводится(): void
    {
        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));

        Livewire::test(CreateBanner::class)
            ->fillForm([
                'name' => 'Без подписи',
                'placement' => Banner::PLACEMENT_HOME,
                'alt' => '',
                'image_path' => [$this->upload()],
                'sort' => 0,
            ])
            ->call('create')
            ->assertHasFormErrors(['alt']);
    }

    /** Значок в меню считает висящие сейчас, а не все заведённые. */
    #[Test]
    public function значок_считает_только_идущие_акции(): void
    {
        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));

        $this->banner(['name' => 'Прошлогодняя', 'ends_at' => Carbon::now()->subMonth()]);
        $this->assertNull(BannerResource::getNavigationBadge(), 'закончившаяся акция в счётчике не нужна');

        $this->banner(['name' => 'Текущая']);
        $this->assertSame('1', BannerResource::getNavigationBadge());
    }
}
