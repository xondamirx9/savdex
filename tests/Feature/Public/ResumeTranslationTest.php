<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Jobs\TranslateResume;
use App\Models\Resume;
use App\Models\User;
use App\Services\MachineTranslator;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Queue;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Резюме переводится на языки площадки.
 *
 * Людей ищут и турецкие, и китайские компании: без перевода
 * английская версия раздела показывала русские должности — то есть
 * не показывала ничего. Переводится должность, текст о себе
 * и места работы; оригинал остаётся тем, что написал человек.
 */
class ResumeTranslationTest extends TestCase
{
    use RefreshDatabase;

    /** Переводчик-заглушка: приписывает язык, ничего не спрашивая. */
    private function fakeTranslator(): void
    {
        $this->app->bind(MachineTranslator::class, fn (): MachineTranslator => new class extends MachineTranslator
        {
            public function translate(string $text, string $to): ?string
            {
                return trim($text) === '' ? null : "[{$to}] {$text}";
            }
        });
    }

    /** @param array<string, mixed> $overrides */
    private function resume(array $overrides = []): Resume
    {
        $resume = new Resume([
            'title' => 'Менеджер по снабжению',
            'about' => 'Семь лет в закупках стройматериалов.',
            'jobs' => [['company' => 'ООО «Стройбаза»', 'position' => 'Снабженец', 'start' => '2019-01', 'end' => '2023-01', 'duties' => 'Закупки цемента.']],
            ...$overrides,
        ]);

        $resume->user_id = User::factory()->create()->id;
        $resume->status = Resume::STATUS_PUBLISHED;
        $resume->published_at = now();
        $resume->saveQuietly();
        $resume->slug = Resume::makeSlug($resume->title, $resume->id);
        $resume->saveQuietly();

        return $resume;
    }

    #[Test]
    public function задача_переводит_должность_текст_и_места_работы(): void
    {
        $this->fakeTranslator();
        $resume = $this->resume();

        (new TranslateResume($resume->id))->handle(app(MachineTranslator::class));

        $resume->refresh();

        $this->assertSame('[en] Менеджер по снабжению', $resume->title_i18n['en']);
        $this->assertSame('[uz] Семь лет в закупках стройматериалов.', $resume->about_i18n['uz']);
        $this->assertSame('[tr] Снабженец', $resume->jobs_i18n['tr'][0]['position']);
        $this->assertSame('[zh] Закупки цемента.', $resume->jobs_i18n['zh'][0]['duties']);
    }

    #[Test]
    public function витрина_отдаёт_перевод_на_языке_посетителя(): void
    {
        $this->fakeTranslator();
        $resume = $this->resume();

        (new TranslateResume($resume->id))->handle(app(MachineTranslator::class));

        $this->get('/en/resume/'.$resume->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('resume.title', '[en] Менеджер по снабжению')
                ->where('resume.about', '[en] Семь лет в закупках стройматериалов.')
                ->where('resume.jobs.0.position', '[en] Снабженец'));

        // Русская версия — оригинал, как написал человек
        $this->get('/resume/'.$resume->slug.'?hl=ru');
        $this->get('/resume/'.$resume->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('resume.title', 'Менеджер по снабжению')
                ->where('resume.jobs.0.position', 'Снабженец'));
    }

    #[Test]
    public function публикация_ставит_перевод_в_очередь(): void
    {
        Queue::fake();
        config(['services.machine_translation.enabled' => true]);

        $user = User::factory()->create();
        $this->actingAs($user)->patch('/cabinet/resume', ['title' => 'Менеджер по снабжению']);

        Queue::assertNothingPushed();

        $this->actingAs($user)->post('/cabinet/resume/publish');

        Queue::assertPushed(TranslateResume::class);
    }

    /** Текст поменяли — старый перевод к нему не относится. */
    #[Test]
    public function правка_текста_снимает_прежний_перевод(): void
    {
        $this->fakeTranslator();
        config(['services.machine_translation.enabled' => false]);

        $resume = $this->resume();
        (new TranslateResume($resume->id))->handle(app(MachineTranslator::class));

        $resume->refresh();
        $this->assertNotEmpty($resume->title_i18n);

        $resume->title = 'Начальник отдела закупок';
        $resume->save();

        $this->assertNull($resume->fresh()->title_i18n);
    }

    /** Список мест правили — перевод к нему больше не привязан. */
    #[Test]
    public function изменившийся_список_мест_показывается_оригиналом(): void
    {
        $this->fakeTranslator();
        $resume = $this->resume();
        (new TranslateResume($resume->id))->handle(app(MachineTranslator::class));

        // Перевод есть, но мест стало два — связь по порядку потеряна
        $resume->refresh();
        $resume->forceFill(['jobs' => [
            ...$resume->jobs,
            ['company' => 'ООО «Цемент»', 'position' => 'Логист', 'start' => '2023-02', 'end' => '', 'duties' => ''],
        ]])->saveQuietly();

        $this->assertSame('Снабженец', $resume->fresh()->localizedJobs('en')[0]['position']);
    }

    #[Test]
    public function добор_находит_непереведённые(): void
    {
        $this->fakeTranslator();
        config(['services.machine_translation.enabled' => false]);

        $translated = $this->resume(['title' => 'Переведённое']);
        $translated->forceFill(['title_i18n' => ['en' => 'a', 'uz' => 'b', 'tr' => 'c', 'zh' => 'd']])->saveQuietly();

        $partial = $this->resume(['title' => 'Наполовину']);
        $partial->forceFill(['title_i18n' => ['en' => 'a']])->saveQuietly();

        $none = $this->resume(['title' => 'Совсем нет']);

        $found = Resume::query()->lackingTranslations()->pluck('id')->all();

        $this->assertContains($partial->id, $found);
        $this->assertContains($none->id, $found);
        $this->assertNotContains($translated->id, $found);
    }
}
