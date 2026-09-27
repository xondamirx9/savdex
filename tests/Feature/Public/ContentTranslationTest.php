<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\NewsPost;
use App\Services\MachineTranslator;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\Http;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Перевод текста из базы, у которого нет своих полей под языки.
 *
 * Переключение языка меняло подписи интерфейса, а описание компании,
 * отзывы и IT-задачи оставались русскими. Теперь первый показ ставит
 * текст в очередь, фоновая задача переводит, следующий показ отдаёт
 * перевод.
 */
class ContentTranslationTest extends TestCase
{
    use RefreshDatabase;

    private function fakeTranslator(string $answer = 'Reliable supplier of cement'): void
    {
        config()->set('services.machine_translation.enabled', true);

        Http::fake([
            'translate.googleapis.com/*' => Http::response([[[$answer, 'оригинал', null]], null, 'ru']),
        ]);
    }

    #[Test]
    public function описание_компании_переводится_фоном_и_приходит_на_языке_витрины(): void
    {
        $this->fakeTranslator();
        $company = Company::factory()->create(['description' => 'Надёжный поставщик цемента']);

        // Русская версия — всегда оригинал и в очередь ничего не ставит.
        // Первой: после захода на «/en/…» язык запоминается, и адрес
        // без префикса уводит редиректом на запомненный
        $this->get('/company/'.$company->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('company.description', 'Надёжный поставщик цемента'));
        $this->assertDatabaseCount('content_translations', 0);

        // Первый показ: перевода ещё нет — оригинал, текст встаёт в очередь
        $this->get('/en/company/'.$company->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('company.description', 'Надёжный поставщик цемента'));

        $this->assertDatabaseHas('content_translations', ['locale' => 'en', 'translation' => null]);

        $this->artisan('translations:fill')->assertSuccessful();

        // На боевом сервере каждый запрос — новый процесс; в тестах
        // приложение одно, и память о переводах прошлого запроса сбрасываем
        $this->app->forgetScopedInstances();

        $this->get('/en/company/'.$company->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('company.description', 'Reliable supplier of cement'));
    }

    #[Test]
    public function неудачный_перевод_повторяется_но_не_вечно(): void
    {
        config()->set('services.machine_translation.enabled', true);
        Http::fake(['translate.googleapis.com/*' => Http::response(null, 500)]);

        $company = Company::factory()->create(['description' => 'Надёжный поставщик цемента']);
        $this->get('/uz/company/'.$company->slug);

        for ($i = 0; $i < 7; $i++) {
            $this->artisan('translations:fill');
        }

        $this->assertDatabaseHas('content_translations', ['locale' => 'uz', 'translation' => null, 'attempts' => 5]);
    }

    /** 429 — переводчик просит подождать: это не повод списывать попытку. */
    #[Test]
    public function ограничение_частоты_не_списывает_попытки(): void
    {
        config()->set('services.machine_translation.enabled', true);
        Http::fake(['translate.googleapis.com/*' => Http::response('Too many requests', 429)]);

        $company = Company::factory()->create(['description' => 'Надёжный поставщик цемента']);
        $this->get('/tr/company/'.$company->slug);

        $this->artisan('translations:fill')->assertSuccessful();

        $this->assertDatabaseHas('content_translations', ['locale' => 'tr', 'translation' => null, 'attempts' => 0]);
    }

    /**
     * Длинный текст новости уходил в адресе запроса, Google отвечал
     * ошибкой 400, и текст оставался русским на всех языках.
     */
    #[Test]
    public function длинный_текст_уходит_телом_запроса_и_кусками(): void
    {
        $this->fakeTranslator('Translated');

        $paragraph = str_repeat('Как проверить поставщика до первой отгрузки. ', 40);
        $text = implode("\n\n", array_fill(0, 5, trim($paragraph)));

        $result = app(MachineTranslator::class)->translate($text, 'en');

        $this->assertNotNull($result);
        Http::assertSent(fn (Request $request): bool => $request->method() === 'POST'
            && mb_strlen((string) ($request->data()['q'] ?? '')) <= 4000
            && ! str_contains($request->url(), 'q='));
        $this->assertGreaterThan(1, count(MachineTranslator::chunks($text)));
    }

    /** Заголовок перевёлся, текст — нет: добор обязан такую новость найти. */
    #[Test]
    public function добор_находит_новость_с_недопереведённым_текстом(): void
    {
        config()->set('services.machine_translation.enabled', false);

        $post = NewsPost::create([
            'slug' => 'test',
            'category' => 'Полезное',
            'title' => 'Заголовок',
            'excerpt' => 'Анонс',
            'body' => 'Текст',
            'is_published' => true,
            'published_at' => now()->subDay(),
        ]);

        $full = ['en' => 'x', 'uz' => 'x', 'tr' => 'x', 'zh' => 'x'];
        $post->forceFill(['title_i18n' => $full, 'excerpt_i18n' => $full, 'body_i18n' => []])->saveQuietly();

        $this->assertTrue(NewsPost::query()->lackingTranslations()->whereKey($post->id)->exists());

        $post->forceFill(['body_i18n' => $full])->saveQuietly();

        $this->assertFalse(NewsPost::query()->lackingTranslations()->whereKey($post->id)->exists());
    }
}
