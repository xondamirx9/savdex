<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Jobs\TranslateListing;
use App\Models\Company;
use App\Models\Listing;
use App\Services\MachineTranslator;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Машинный перевод объявлений.
 *
 * Продавцы пишут по-русски, каталог работает на пяти языках:
 * перевод заголовка и описания делается фоном после публикации,
 * хранится в объявлении и показывается на языке посетителя.
 * Пока перевода нет — оригинал: русский текст лучше пустой карточки.
 */
class ListingTranslationTest extends TestCase
{
    use RefreshDatabase;

    private function fakeTranslator(): void
    {
        config()->set('services.machine_translation.enabled', true);

        Http::fake([
            'translate.googleapis.com/*' => Http::response([
                [['Cement breeze blocks', 'Цементные бриз-блоки', null]],
                null,
                'ru',
            ]),
        ]);
    }

    private function listing(): Listing
    {
        return Listing::factory()->create([
            'company_id' => Company::factory()->create(['status' => 'active'])->id,
            'title' => 'Цементные бриз-блоки',
            'description' => 'Блоки для вентилируемых фасадов.',
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'expires_at' => now()->addDays(30),
        ]);
    }

    #[Test]
    public function публикация_переводит_заголовок_и_описание(): void
    {
        $this->fakeTranslator();

        // Очередь в тестах синхронная: dispatch из saved-хука выполнится сразу
        $listing = $this->listing()->fresh();

        $this->assertSame('Cement breeze blocks', $listing->title_i18n['en'] ?? null);
        $this->assertArrayHasKey('uz', $listing->title_i18n);
        $this->assertArrayHasKey('en', $listing->description_i18n);
    }

    #[Test]
    public function каталог_показывает_заголовок_на_языке_посетителя(): void
    {
        $this->fakeTranslator();
        $listing = $this->listing();

        // Сначала русская версия: после «/en/…» сессия запоминает язык,
        // и «/catalog» без префикса уводился бы редиректом
        $this->get('/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listings.data.0.title', 'Цементные бриз-блоки'));

        $this->get('/en/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listings.data.0.title', 'Cement breeze blocks'));
    }

    /** Перевода нет (сервис недоступен) — показывается оригинал. */
    #[Test]
    public function без_перевода_показывается_оригинал(): void
    {
        $listing = $this->listing();

        $this->assertNull($listing->fresh()->title_i18n);

        $this->get('/en/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listings.data.0.title', 'Цементные бриз-блоки'));
    }

    /** Переведённый заголовок попадает в поисковый индекс. */
    #[Test]
    public function перевод_ищется_в_каталоге(): void
    {
        $this->fakeTranslator();
        $this->listing();

        $this->get('/catalog?q=cement+breeze')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 1));
    }

    /** Сервис вернул ошибку — объявление публикуется без переводов. */
    #[Test]
    public function сбой_переводчика_не_ломает_публикацию(): void
    {
        config()->set('services.machine_translation.enabled', true);
        Http::fake(['translate.googleapis.com/*' => Http::response(null, 500)]);

        $listing = $this->listing()->fresh();

        $this->assertSame([], $listing->title_i18n);
        $this->assertSame('Цементные бриз-блоки', $listing->localizedTitle('en'));
    }

    /**
     * Добор по расписанию видит не только «переводов нет», но и «не все»:
     * из книги или из админки приходит один английский, остальные
     * языки должен доделать переводчик.
     */
    #[Test]
    public function добор_находит_частично_переведённые(): void
    {
        $none = Listing::factory()->create(['title_i18n' => null]);
        $empty = Listing::factory()->create(['title_i18n' => []]);
        $partial = Listing::factory()->create(['title_i18n' => ['en' => 'Cement']]);
        $full = Listing::factory()->create([
            'title_i18n' => ['en' => 'Cement', 'uz' => 'Sement', 'tr' => 'Çimento', 'zh' => '水泥'],
        ]);

        $found = Listing::query()->lackingTranslations()->pluck('id')->all();

        $this->assertEqualsCanonicalizing([$none->id, $empty->id, $partial->id], $found);
        $this->assertNotContains($full->id, $found);
    }

    /**
     * Пока задача ходила к переводчику, администратор вписал перевод
     * руками. Снимок задачи старше базы — база выигрывает.
     */
    #[Test]
    public function перевод_из_очереди_не_затирает_вписанный_руками(): void
    {
        config()->set('services.machine_translation.enabled', false);
        $listing = $this->listing();

        $translator = new class($listing) extends MachineTranslator
        {
            public function __construct(private readonly Listing $listing) {}

            public function translate(string $text, string $to): ?string
            {
                // Первый же запрос: администратор успел сохранить свой перевод
                if ($to === 'en') {
                    Listing::query()->whereKey($this->listing->id)
                        ->update(['title_i18n' => json_encode(['en' => 'Manual title'])]);
                }

                return 'Machine '.$to;
            }
        };

        (new TranslateListing($listing->id))->handle($translator);

        $fresh = $listing->fresh();

        $this->assertSame('Manual title', $fresh->title_i18n['en']);
        $this->assertSame('Machine uz', $fresh->title_i18n['uz']);
    }

    /** Условия поставки и оплаты тоже переводятся — и доходят до страницы. */
    #[Test]
    public function условия_на_странице_объявления_на_языке_посетителя(): void
    {
        $listing = $this->listing();
        $listing->forceFill([
            'delivery_terms' => 'Самовывоз со склада',
            'delivery_terms_i18n' => ['en' => 'Pick-up from the warehouse'],
        ])->save();

        $this->get('/listing/'.$listing->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listing.delivery_terms', 'Самовывоз со склада'));

        $this->get('/en/listing/'.$listing->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listing.delivery_terms', 'Pick-up from the warehouse'));
    }

    #[Test]
    public function повторный_запуск_не_перезапрашивает_готовые_переводы(): void
    {
        $this->fakeTranslator();
        $listing = $this->listing()->fresh();

        Http::fake(fn () => throw new \RuntimeException('лишний запрос к переводчику'));

        (new TranslateListing($listing->id))->handle(app(MachineTranslator::class));

        $this->assertSame('Cement breeze blocks', $listing->fresh()->title_i18n['en']);
    }
}
