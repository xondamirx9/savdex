<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Listing;
use App\Models\ListingStat;
use App\Models\SearchHit;
use App\Support\StatsRecorder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Цена показа страницы каталога и честность счётчиков.
 *
 * Статистика пишется на анонимный GET, поэтому её стоимость в запросах
 * и её накручиваемость — не абстракции: на счётчиках держится платная
 * аналитика и расчёт эффекта продвижения.
 */
class StatsRecordingTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create();
    }

    /** @param array<string, mixed> $overrides */
    private function listing(array $overrides = []): Listing
    {
        return Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'impressions_count' => 0,
            'views_count' => 0,
            ...$overrides,
        ]);
    }

    /**
     * Заход на страницу и её обновление тем же посетителем.
     *
     * Куку сессии приходится проносить руками: тестовый клиент её не
     * хранит и на каждый get() заводит новую сессию — то есть изображает
     * не обновление страницы, а нового посетителя. Браузер куку хранит
     * сам и попадает ровно в проверяемую ветку.
     */
    private function revisit(string $url, int $times): void
    {
        $this->get($url);

        $cookie = config('session.cookie');
        $id = $this->app['session']->getId();

        foreach (range(2, $times) as $ignored) {
            $this->withCookie($cookie, $id)->get($url);
        }
    }

    /**
     * Обновление страницы не должно давать новый показ.
     *
     * Раньше дедупликации не было вовсе: F5 на собственном объявлении
     * поднимал счётчик, а он продаётся продавцу как аналитика и лежит
     * в основе расчёта эффекта продвижения.
     */
    #[Test]
    public function повторный_заход_не_накручивает_показы(): void
    {
        $listing = $this->listing();

        $this->revisit('/catalog', times: 3);

        $this->assertSame(1, $listing->fresh()->impressions_count);
        $this->assertSame(1, ListingStat::where('listing_id', $listing->id)->value('impressions'));
    }

    #[Test]
    public function повторный_просмотр_карточки_не_накручивает_просмотры(): void
    {
        $listing = $this->listing();

        $this->revisit("/listing/{$listing->slug}", times: 2);

        $this->assertSame(1, $listing->fresh()->views_count);
    }

    /** Разные объявления в одной выдаче считаются каждое, а не одно. */
    #[Test]
    public function дедупликация_не_склеивает_разные_объявления(): void
    {
        $first = $this->listing();
        $second = $this->listing();

        $this->get('/catalog');

        $this->assertSame(1, $first->fresh()->impressions_count);
        $this->assertSame(1, $second->fresh()->impressions_count);
    }

    /** Другой посетитель — другой показ: дедупликация не должна глушить всех. */
    #[Test]
    public function другой_посетитель_считается_отдельно(): void
    {
        $listing = $this->listing();

        // Разные сессии — как заходы с двух устройств
        $this->get('/catalog');
        $this->get('/catalog');

        $this->assertSame(2, $listing->fresh()->impressions_count);
    }

    /**
     * Двадцать объявлений в выдаче не должны стоить сорока запросов.
     *
     * Раньше строки дневной статистики создавались циклом firstOrCreate,
     * и один анонимный заход на поиск давал под полсотни записей в базу.
     */
    #[Test]
    public function страница_каталога_не_плодит_запросы(): void
    {
        Listing::factory()->count(20)->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
        ]);

        $queries = 0;
        DB::listen(function () use (&$queries): void {
            $queries++;
        });

        $this->get('/catalog?q='.urlencode('цемент'));

        $this->assertLessThan(
            30,
            $queries,
            "Страница каталога выполнила {$queries} запросов — статистика снова пишется по одной строке",
        );
    }

    #[Test]
    public function поисковый_запрос_засчитывается_компании(): void
    {
        $this->listing(['title' => 'Цемент М400 навалом мешками']);

        $this->get('/catalog?q='.urlencode('Цемент'));

        $hit = SearchHit::where('company_id', $this->company->id)->first();

        $this->assertNotNull($hit);
        $this->assertSame('цемент', $hit->query, 'запрос нормализуется по регистру');
        $this->assertSame(1, $hit->impressions);
    }

    /** Раскрытие контакта — событие оплаченное, его дедупликация не касается. */
    #[Test]
    public function раскрытия_считаются_всегда(): void
    {
        $listing = $this->listing(['unlocks_count' => 0]);

        app(StatsRecorder::class)->unlock($listing);
        app(StatsRecorder::class)->unlock($listing);

        $this->assertSame(2, $listing->fresh()->unlocks_count);
    }
}
