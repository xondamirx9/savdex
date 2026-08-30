<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Listing;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Поиск в обеих графиках: узбекская аудитория набирает латиницей
 * («sement», «armatura», «gisht»), а объявления пишутся кириллицей —
 * и наоборот. Прямой LIKE давал латинским запросам пустую выдачу
 * всегда, независимо от наполнения каталога (аудит, п. 5.4).
 */
class SearchTransliterationTest extends TestCase
{
    use RefreshDatabase;

    private function listing(string $title): Listing
    {
        return Listing::factory()->create([
            'company_id' => Company::factory()->create(['status' => 'active'])->id,
            'title' => $title,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'expires_at' => now()->addDays(30),
        ]);
    }

    #[Test]
    public function латинский_запрос_находит_кириллическое_объявление(): void
    {
        $this->listing('Цемент М400 навалом');

        $this->get('/catalog?q=sement')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Цемент М400 навалом'));

        $this->get('/catalog?q=armatura')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 0));
    }

    #[Test]
    public function кириллический_запрос_находит_латинское_объявление(): void
    {
        $this->listing("G'isht keramik");

        $this->get('/catalog?q='.urlencode('гишт'))
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 1));
    }

    /** «g'isht», «gʻisht» и «gisht» — один и тот же запрос. */
    #[Test]
    public function узбекский_апостроф_не_мешает_поиску(): void
    {
        $this->listing("G'isht keramik");

        $this->get('/catalog?q=gisht')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 1));

        $this->get('/catalog?q='.urlencode("g'isht"))
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 1));
    }

    #[Test]
    public function компания_находится_латиницей(): void
    {
        Company::factory()->create(['name' => 'Цемент Трейд', 'status' => 'active']);

        $this->get('/companies?q=sement')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('companies.data', 1));
    }
}
