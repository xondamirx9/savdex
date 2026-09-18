<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Resume;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * «Моё резюме» — бесплатный раздел для соискателя.
 *
 * Резюме одно на человека: меню кабинета называется «Моё резюме»,
 * и второе завести нельзя. Черновик виден только владельцу,
 * опубликованное — компаниям площадки.
 */
class ResumeTest extends TestCase
{
    use RefreshDatabase;

    /** @param array<string, mixed> $overrides */
    private function payload(array $overrides = []): array
    {
        return [
            'title' => 'Менеджер по снабжению',
            'field' => 'procurement',
            'salary' => 8_000_000,
            'currency' => 'UZS',
            'employment' => ['full'],
            'schedule' => ['full_day'],
            'about' => 'Семь лет в закупках стройматериалов.',
            'skills' => ['1C', 'Переговоры', ''],
            'jobs' => [
                ['company' => 'ООО «Стройбаза»', 'position' => 'Снабженец', 'start' => '2019-01', 'end' => '2023-01', 'duties' => 'Закупки цемента.'],
                ['company' => '', 'position' => '', 'start' => '', 'end' => '', 'duties' => ''],
            ],
            'education' => [['institution' => 'ТГЭУ', 'faculty' => 'Логистика', 'level' => 'bachelor', 'year' => 2016]],
            'languages' => [['name' => 'Русский', 'level' => 'native']],
            'contact_name' => 'Максуд Максудов',
            'contact_phone' => '+998 90 123-45-67',
            'contact_email' => 'maksud@example.com',
            'show_phone' => true,
            'show_email' => false,
            ...$overrides,
        ];
    }

    #[Test]
    public function резюме_создаётся_и_опыт_считается_из_мест_работы(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)->patch('/cabinet/resume', $this->payload())->assertRedirect();

        $resume = Resume::query()->firstOrFail();

        $this->assertSame($user->id, $resume->user_id);
        $this->assertSame('Менеджер по снабжению', $resume->title);
        $this->assertSame(Resume::STATUS_DRAFT, $resume->status);
        $this->assertSame(48, $resume->experience_months);
        $this->assertNotEmpty($resume->slug);

        // Пустые строки списков и навыков выкинуты
        $this->assertCount(1, $resume->jobs);
        $this->assertSame(['1C', 'Переговоры'], $resume->skills);
    }

    #[Test]
    public function резюме_одно_на_человека(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)->patch('/cabinet/resume', $this->payload());
        $this->actingAs($user)->patch('/cabinet/resume', $this->payload(['title' => 'Логист']));

        $this->assertSame(1, Resume::count());
        $this->assertSame('Логист', Resume::query()->value('title'));
    }

    /** Незаконченное место работы считается по сегодняшний день. */
    #[Test]
    public function текущая_работа_считается_до_сегодня(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)->patch('/cabinet/resume', $this->payload([
            'jobs' => [[
                'company' => 'ООО «Стройбаза»',
                'position' => 'Снабженец',
                'start' => now()->subMonths(30)->format('Y-m'),
                'end' => '',
                'duties' => '',
            ]],
        ]));

        $this->assertEqualsWithDelta(30, Resume::query()->value('experience_months'), 1);
    }

    /** Два места в одно время не удваивают стаж. */
    #[Test]
    public function пересекающиеся_места_не_складываются_дважды(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)->patch('/cabinet/resume', $this->payload([
            'jobs' => [
                ['company' => 'A', 'position' => 'Снабженец', 'start' => '2020-01', 'end' => '2022-01', 'duties' => ''],
                ['company' => 'B', 'position' => 'Логист', 'start' => '2021-01', 'end' => '2022-01', 'duties' => ''],
            ],
        ]));

        $this->assertSame(24, Resume::query()->value('experience_months'));
    }

    #[Test]
    public function публикация_и_снятие_бесплатны_и_мгновенны(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user)->patch('/cabinet/resume', $this->payload());

        $this->actingAs($user)->post('/cabinet/resume/publish')->assertRedirect();

        $resume = Resume::query()->firstOrFail();
        $this->assertSame(Resume::STATUS_PUBLISHED, $resume->status);
        $this->assertNotNull($resume->published_at);

        $this->actingAs($user)->post('/cabinet/resume/hide');

        $this->assertSame(Resume::STATUS_HIDDEN, Resume::query()->value('status'));
    }

    /** Снятое модерацией сам соискатель обратно не вернёт. */
    #[Test]
    public function снятое_модерацией_не_публикуется_обратно(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user)->patch('/cabinet/resume', $this->payload());

        Resume::query()->update(['status' => Resume::STATUS_BLOCKED]);

        $this->actingAs($user)->post('/cabinet/resume/publish')->assertSessionHasErrors('status');

        $this->assertSame(Resume::STATUS_BLOCKED, Resume::query()->value('status'));
    }

    #[Test]
    public function страница_кабинета_открывается_и_подставляет_контакты_профиля(): void
    {
        $user = User::factory()->create(['name' => 'Максуд Максудов', 'email' => 'maksud@example.com']);

        $this->actingAs($user)->get('/cabinet/resume')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('cabinet/Resume')
                ->where('resume', null)
                ->where('defaults.contact_name', 'Максуд Максудов')
                ->where('defaults.contact_email', 'maksud@example.com')
                ->has('options.fields'));
    }

    #[Test]
    public function чужого_резюме_кабинет_не_показывает(): void
    {
        $owner = User::factory()->create();
        $this->actingAs($owner)->patch('/cabinet/resume', $this->payload());

        $other = User::factory()->create();

        $this->actingAs($other)->get('/cabinet/resume')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('resume', null));

        $this->actingAs($other)->post('/cabinet/resume/publish')->assertNotFound();
    }

    #[Test]
    public function резюме_удаляется(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user)->patch('/cabinet/resume', $this->payload());

        $this->actingAs($user)->delete('/cabinet/resume')->assertRedirect();

        $this->assertSame(0, Resume::count());
    }

    #[Test]
    public function гостя_на_страницу_не_пускают(): void
    {
        $this->get('/cabinet/resume')->assertRedirect('/login');
    }
}
