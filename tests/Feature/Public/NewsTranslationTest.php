<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\NewsPost;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Перевод новостей на языки витрины.
 *
 * Новость пишется по-русски, площадка работает на пяти языках:
 * раздел «Новости» на узбекской версии показывал русский текст,
 * потому что переводить его было нечем. Схема — как у объявлений:
 * перевод делается фоном после публикации и хранится в новости.
 */
class NewsTranslationTest extends TestCase
{
    use RefreshDatabase;

    private function fakeTranslator(): void
    {
        config()->set('services.machine_translation.enabled', true);

        Http::fake([
            'translate.googleapis.com/*' => Http::response([
                [['Yangi tariflar', 'Новые тарифы', null]],
                null,
                'ru',
            ]),
        ]);
    }

    private function newsPost(): NewsPost
    {
        return NewsPost::create([
            'slug' => 'novye-tarify',
            'category' => 'Тарифы и оплата',
            'title' => 'Новые тарифы',
            'excerpt' => 'Что изменилось в ценах',
            'body' => 'С первого числа тарифы обновлены.',
            'is_published' => true,
            'published_at' => now()->subDay(),
        ]);
    }

    #[Test]
    public function публикация_переводит_новость(): void
    {
        $this->fakeTranslator();

        // Очередь в тестах синхронная: dispatch из saved-хука выполнится сразу
        $post = $this->newsPost()->fresh();

        $this->assertSame('Yangi tariflar', $post->title_i18n['uz'] ?? null);
        $this->assertSame('Yangi tariflar', $post->localizedTitle('uz'));

        // Русская версия всегда показывает оригинал
        $this->assertSame('Новые тарифы', $post->localizedTitle('ru'));
    }

    #[Test]
    public function без_перевода_показывается_оригинал(): void
    {
        config()->set('services.machine_translation.enabled', false);

        $post = $this->newsPost()->fresh();

        $this->assertNull($post->title_i18n);
        $this->assertSame('Новые тарифы', $post->localizedTitle('uz'));
    }

    #[Test]
    public function страница_новостей_отдаёт_перевод_и_рубрику_на_языке_витрины(): void
    {
        $this->fakeTranslator();
        $this->newsPost();

        $this->get('/uz/news')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('posts.0.title', 'Yangi tariflar')
            // Рубрика из словаря: она выбирается из списка, а не пишется руками
            ->where('posts.0.category_label', 'Tariflar va to‘lov')
            // Исходное значение остаётся: по нему обложка выбирает оформление
            ->where('posts.0.category', 'Тарифы и оплата')
            ->where('categories.0.label', 'Tariflar va to‘lov'));
    }

    /**
     * Текст страницы «О компании» рисует React по словарю, поэтому
     * проверяется словарь, который уезжает на страницу, а не разметка:
     * в разметке он лежит JSON-ом с экранированными символами.
     */
    #[Test]
    public function страница_о_компании_приходит_со_словарём_нужного_языка(): void
    {
        // Русский первым: после захода на «/uz/…» язык запоминается,
        // и безпрефиксный адрес уводит редиректом на запомненный
        $this->get('/about')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('translations.about.title', 'О компании'));

        $this->get('/uz/about')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('translations.about.title', 'Kompaniya haqida')
            ->where('translations.about.nav.rules', 'Joylashtirish qoidalari'));

        $this->get('/tr/about')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('translations.about.title', 'Şirket hakkında'));

        $this->get('/zh/about')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('translations.about.title', '关于公司'));
    }

    /** Словарь не должен разъезжаться: пропущенный ключ виден как «about.faq.q3». */
    #[Test]
    public function словари_пяти_языков_совпадают_по_ключам(): void
    {
        $reference = $this->keys((array) trans('ui', locale: 'ru'));

        foreach (['en', 'uz', 'tr', 'zh'] as $locale) {
            $this->assertSame(
                $reference,
                $this->keys((array) trans('ui', locale: $locale)),
                "Словарь {$locale} разошёлся с русским",
            );
        }
    }

    /**
     * Плоский список ключей словаря: «about.faq.q1».
     *
     * @param  array<string, mixed>  $dictionary
     * @return list<string>
     */
    private function keys(array $dictionary, string $prefix = ''): array
    {
        $keys = [];

        foreach ($dictionary as $key => $value) {
            $path = $prefix === '' ? (string) $key : $prefix.'.'.$key;

            if (is_array($value)) {
                $keys = [...$keys, ...$this->keys($value, $path)];

                continue;
            }

            $keys[] = $path;
        }

        sort($keys);

        return $keys;
    }
}
