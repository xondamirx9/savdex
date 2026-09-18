<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Banner;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Сроки показа баннера.
 *
 * Ради этого баннеры и заводятся из админки: акцию готовят заранее,
 * а заканчивается она сама. Баннер, провисевший лишний день, — это
 * обещание, которого площадка уже не выполняет, и снимать его вручную
 * в выходные никто не станет.
 */
class BannerScheduleTest extends TestCase
{
    use RefreshDatabase;

    private function banner(array $attrs = []): Banner
    {
        return Banner::query()->create(array_merge([
            'name' => 'Осенняя акция',
            'placement' => Banner::PLACEMENT_HOME,
            'alt' => 'Скидка 30% на годовой тариф',
            'image_path' => 'banners/autumn.webp',
        ], $attrs));
    }

    // ── Планирование ────────────────────────────────────────────────

    /** Заведён 29 сентября на 1 октября — до срока не показывается. */
    #[Test]
    public function запланированный_баннер_ждёт_своей_даты(): void
    {
        $banner = $this->banner([
            'starts_at' => Carbon::parse('2026-10-01 00:00'),
            'ends_at' => Carbon::parse('2026-10-30 23:59'),
        ]);

        $this->assertFalse($banner->isLive(Carbon::parse('2026-09-29 12:00')), 'до старта висеть не должен');
        $this->assertTrue($banner->isLive(Carbon::parse('2026-10-01 00:01')));
        $this->assertTrue($banner->isLive(Carbon::parse('2026-10-30 12:00')));
    }

    /** Срок вышел — исчезает сам, без участия человека. */
    #[Test]
    public function истёкший_баннер_пропадает_сам(): void
    {
        $banner = $this->banner(['ends_at' => Carbon::parse('2026-10-30 23:59')]);

        $this->assertTrue($banner->isLive(Carbon::parse('2026-10-30 23:58')));
        $this->assertFalse($banner->isLive(Carbon::parse('2026-10-31 00:00')), 'после срока висеть не должен');
    }

    /** Без дат — бессрочный. */
    #[Test]
    public function баннер_без_дат_показывается_всегда(): void
    {
        $this->assertTrue($this->banner()->isLive());
    }

    /** Выключатель сильнее дат: снять с показа, не трогая сроки. */
    #[Test]
    public function выключенный_не_показывается_даже_в_свой_срок(): void
    {
        $banner = $this->banner([
            'is_active' => false,
            'starts_at' => Carbon::parse('2026-10-01 00:00'),
            'ends_at' => Carbon::parse('2026-10-30 23:59'),
        ]);

        $this->assertFalse($banner->isLive(Carbon::parse('2026-10-15 12:00')));
    }

    /** Выборка для страницы обязана слушаться тех же правил. */
    #[Test]
    public function выборка_места_берёт_только_живые(): void
    {
        $now = Carbon::parse('2026-10-15 12:00');

        $this->banner(['name' => 'Прошлая', 'ends_at' => Carbon::parse('2026-10-01 00:00')]);
        $this->banner(['name' => 'Будущая', 'starts_at' => Carbon::parse('2026-11-01 00:00')]);
        $this->banner(['name' => 'Выключенная', 'is_active' => false]);
        $live = $this->banner(['name' => 'Текущая']);

        $found = Banner::forPlacement(Banner::PLACEMENT_HOME, $now);

        $this->assertNotNull($found);
        $this->assertSame($live->id, $found->id);
    }

    // ── Два баннера на одном месте ──────────────────────────────────

    /** Показывается один, с меньшим «порядком». */
    #[Test]
    public function из_двух_баннеров_места_показывается_приоритетный(): void
    {
        $this->banner(['name' => 'Обычная', 'sort' => 10]);
        $main = $this->banner(['name' => 'Главная акция', 'sort' => 1]);

        $this->assertSame($main->id, Banner::forPlacement(Banner::PLACEMENT_HOME)?->id);
    }

    /** Баннер другого места на чужое не лезет. */
    #[Test]
    public function места_не_смешиваются(): void
    {
        $this->banner(['placement' => Banner::PLACEMENT_CATALOG]);

        $this->assertNull(Banner::forPlacement(Banner::PLACEMENT_HOME));
    }

    // ── Обратный отсчёт ─────────────────────────────────────────────

    #[Test]
    public function обратный_отсчёт_говорит_человеческой_фразой(): void
    {
        $now = Carbon::parse('2026-10-28 12:00');

        $cases = [
            ['ends_at' => Carbon::parse('2026-10-30 12:00'), 'ожидание' => 'осталось 2 дня'],
            ['ends_at' => Carbon::parse('2026-10-29 12:00'), 'ожидание' => 'осталось 1 день'],
            ['ends_at' => Carbon::parse('2026-10-28 15:00'), 'ожидание' => 'осталось 3 часа'],
            ['ends_at' => Carbon::parse('2026-10-28 12:30'), 'ожидание' => 'меньше часа'],
            ['ends_at' => Carbon::parse('2026-10-01 12:00'), 'ожидание' => 'закончилась'],
            ['ends_at' => null, 'ожидание' => 'бессрочно'],
        ];

        foreach ($cases as $case) {
            $banner = $this->banner(['ends_at' => $case['ends_at']]);

            $this->assertSame($case['ожидание'], $banner->countdown($now));
        }
    }

    /** У запланированного отсчёт показывает не конец, а старт. */
    #[Test]
    public function у_запланированного_отсчёт_показывает_старт(): void
    {
        $banner = $this->banner([
            'starts_at' => Carbon::parse('2026-10-01 00:00'),
            'ends_at' => Carbon::parse('2026-10-30 23:59'),
        ]);

        $this->assertStringContainsString('старт', $banner->countdown(Carbon::parse('2026-09-29 12:00')));
    }
}
