<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Banner;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Storage;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Баннеры: пункт меню и правила модели.
 *
 * Раздел с этапа 2 переноса работает на Python
 * (python/savdex/site/admin.py, проверки формы, картинок, сроков и
 * предпросмотра — python/tests/test_banners_admin.py). Здесь — пункт
 * меню со значком и то, что обязано держаться в модели Laravel: она
 * по-прежнему читает баннеры для витрины.
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

    // ── Экраны ──────────────────────────────────────────────────────

    private const LINK = '/admin/python?next=/py/admin/site/banner/';

    /** Баннеры — тот же content, что страницы и новости (§4 ТЗ). */
    #[Test]
    public function пункт_баннеров_видят_те_же_кто_правит_контент(): void
    {
        foreach ([AdminAccess::SUPERADMIN, AdminAccess::ADMIN, AdminAccess::CONTENT_MANAGER] as $role) {
            $this->actingAs($this->admin($role));

            $this->get('/admin')->assertSee(self::LINK, false);
        }

        foreach ([AdminAccess::SALES, AdminAccess::FINANCE, AdminAccess::MODERATOR, AdminAccess::SUPPORT] as $role) {
            $this->actingAs($this->admin($role));

            $this->get('/admin')->assertDontSee(self::LINK, false);
        }
    }

    /** Значок у пункта меню считает висящие сейчас, а не все заведённые. */
    #[Test]
    public function значок_считает_только_идущие_акции(): void
    {
        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));

        $this->banner(['name' => 'Прошлогодняя', 'ends_at' => Carbon::now()->subMonth()]);
        $this->banner(['name' => 'Будущая', 'starts_at' => Carbon::now()->addWeek()]);
        $this->banner(['name' => 'Текущая']);

        $html = $this->get('/admin')->getContent();
        $item = substr($html, (int) strpos($html, self::LINK), 3000);

        $this->assertMatchesRegularExpression('/>\s*1\s*</', $item, 'в значке — одна идущая акция');
    }

    // ── Файлы ───────────────────────────────────────────────────────

    /**
     * Снятая акция уносит свои файлы.
     *
     * Диск на сервере постоянный и небольшой, а про картинку удалённого
     * баннера не вспомнит уже никто.
     */
    #[Test]
    public function удаление_баннера_убирает_файлы(): void
    {
        Storage::disk('public')->put('banners/wide.webp', 'x');
        Storage::disk('public')->put('banners/narrow.webp', 'x');
        Storage::disk('public')->put('banners/ru.webp', 'x');

        $banner = $this->banner([
            'image_path' => 'banners/wide.webp',
            'image_mobile_path' => 'banners/narrow.webp',
        ]);

        $banner->images()->create(['locale' => 'ru', 'image_path' => 'banners/ru.webp']);

        $banner->delete();

        Storage::disk('public')->assertMissing('banners/wide.webp');
        Storage::disk('public')->assertMissing('banners/narrow.webp');
        Storage::disk('public')->assertMissing('banners/ru.webp');
    }

    /** Замена картинки убирает прежнюю — иначе правка баннера копит мусор. */
    #[Test]
    public function замена_картинки_убирает_прежнюю(): void
    {
        Storage::disk('public')->put('banners/old.webp', 'x');
        Storage::disk('public')->put('banners/new.webp', 'x');

        $banner = $this->banner(['image_path' => 'banners/old.webp']);

        $banner->update(['image_path' => 'banners/new.webp']);

        Storage::disk('public')->assertMissing('banners/old.webp');
        Storage::disk('public')->assertExists('banners/new.webp');
    }
}
