<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Banners\Pages\CreateBanner;
use App\Models\AdminAction;
use App\Models\Banner;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Время в админке — ташкентское.
 *
 * Поля даты-времени в формах админки понимали введённое как UTC:
 * администратор ставил начало акции «16:00» по своим часам, в базу
 * ложилось 16:00 UTC — то есть 21:00 в Ташкенте. Баннер «с сейчас»
 * появлялся через пять часов, и на столько же дольше висел после
 * конца акции. Таблица баннеров при этом показывала время уже
 * по Ташкенту, и расхождение выглядело как «баннер не работает».
 *
 * Тем же страдали все девять полей даты-времени в админке: срок
 * объявления, дедлайн тендера, публикация новости, задачи CRM.
 */
class AdminTimezoneTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        Storage::fake('public');

        $this->actingAs(User::factory()->create([
            'is_admin' => true,
            'admin_role' => AdminAccess::SUPERADMIN,
            'status' => 'active',
        ]));
    }

    private function createBanner(array $dates): Banner
    {
        Livewire::test(CreateBanner::class)
            ->fillForm([
                'name' => 'Осенняя акция',
                'placement' => Banner::PLACEMENT_HOME,
                'alt' => 'Скидка 30%',
                'sort' => 0,
                'image_path' => UploadedFile::fake()->image('banner.jpg', 2400, 800),
                ...$dates,
            ])
            ->call('create')
            ->assertHasNoFormErrors();

        return Banner::query()->firstOrFail();
    }

    #[Test]
    public function баннер_с_сейчас_появляется_сразу(): void
    {
        Carbon::setTestNow('2026-09-26 11:00:00'); // 16:00 в Ташкенте

        // Администратор смотрит на свои часы: 16:00
        $banner = $this->createBanner([
            'starts_at' => '2026-09-26 16:00:00',
            'ends_at' => '2026-10-01 00:00:00',
        ]);

        $this->assertTrue($banner->isLive(), 'Баннер, заведённый «с сейчас», не показывается');

        $this->get('/')->assertInertia(
            fn ($page) => $page->where('banner.alt', 'Скидка 30%'),
        );
    }

    #[Test]
    public function в_базу_ложится_utc(): void
    {
        $banner = $this->createBanner([
            'starts_at' => '2026-10-01 09:00:00',
            'ends_at' => '2026-10-07 23:59:00',
        ]);

        // 09:00 в Ташкенте — это 04:00 UTC
        $this->assertSame('2026-10-01 04:00:00', $banner->getRawOriginal('starts_at'));
        $this->assertSame('2026-10-07 18:59:00', $banner->getRawOriginal('ends_at'));
    }

    #[Test]
    public function акция_кончается_вовремя_а_не_на_пять_часов_позже(): void
    {
        $this->createBanner([
            'starts_at' => '2026-09-01 00:00:00',
            'ends_at' => '2026-10-01 00:00:00', // полночь по Ташкенту
        ]);

        // 00:30 по Ташкенту, первое октября: акция уже кончилась
        Carbon::setTestNow('2026-09-30 19:30:00');

        $this->assertFalse(Banner::query()->firstOrFail()->isLive());
    }

    /**
     * Уже заведённые баннеры исправляются миграцией.
     *
     * Правка формы действует только на новые правки. Без миграции
     * старый баннер так и остался бы сдвинутым на пять часов.
     */
    #[Test]
    public function миграция_исправляет_уже_заведённые_баннеры(): void
    {
        // Так записала сломанная форма: «16:00 по Ташкенту» как 16:00 UTC
        $id = DB::table('banners')->insertGetId([
            'name' => 'Старая акция',
            'placement' => Banner::PLACEMENT_HOME,
            'alt' => 'Скидка',
            'image_path' => 'banners/old.webp',
            'starts_at' => '2026-09-26 16:00:00',
            'ends_at' => '2026-10-01 00:00:00',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $withoutDates = DB::table('banners')->insertGetId([
            'name' => 'Бессрочная',
            'placement' => Banner::PLACEMENT_CATALOG,
            'alt' => 'Всегда',
            'image_path' => 'banners/always.webp',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $migration = require database_path('migrations/2026_09_26_120000_fix_banner_times_entered_as_utc.php');
        $migration->up();

        $fixed = Banner::query()->findOrFail($id);

        $this->assertSame('2026-09-26 11:00:00', $fixed->getRawOriginal('starts_at'));
        $this->assertSame('2026-09-30 19:00:00', $fixed->getRawOriginal('ends_at'));

        // Пустые сроки остаются пустыми: «сразу» и «бессрочно»
        $untouched = Banner::query()->findOrFail($withoutDates);
        $this->assertNull($untouched->starts_at);
        $this->assertNull($untouched->ends_at);

        // И откат возвращает как было
        $migration->down();

        $this->assertSame('2026-09-26 16:00:00', Banner::query()->findOrFail($id)->getRawOriginal('starts_at'));
    }

    /**
     * Исправление данных — не действие администратора.
     *
     * Через модель миграция записала бы в журнал «кто-то изменил
     * баннер» без автора, и через месяц это выглядело бы загадкой.
     */
    #[Test]
    public function миграция_не_пишет_в_журнал_действий(): void
    {
        DB::table('banners')->insert([
            'name' => 'Старая акция',
            'placement' => Banner::PLACEMENT_HOME,
            'alt' => 'Скидка',
            'image_path' => 'banners/old.webp',
            'starts_at' => '2026-09-26 16:00:00',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $before = AdminAction::query()->count();

        (require database_path('migrations/2026_09_26_120000_fix_banner_times_entered_as_utc.php'))->up();

        $this->assertSame($before, AdminAction::query()->count());
    }
}
