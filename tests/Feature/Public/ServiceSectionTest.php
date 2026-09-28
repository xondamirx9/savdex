<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\ItTask;
use App\Models\Resume;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Collection;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Страницы направлений «Доп. услуг» — из подменю в шапке.
 *
 * У каждого направления своя страница: задачи, исполнители, у HR —
 * резюме. Чужие задачи и исполнители на неё не попадают.
 */
class ServiceSectionTest extends TestCase
{
    use RefreshDatabase;

    /** @return array<string, array{string}> */
    public static function страницы(): array
    {
        return array_combine(
            array_keys(ItTask::SERVICE_PAGES),
            array_map(fn (string $slug): array => [$slug], array_keys(ItTask::SERVICE_PAGES)),
        );
    }

    #[Test]
    #[DataProvider('страницы')]
    public function страница_направления_открывается(string $slug): void
    {
        $this->get('/services/'.$slug)
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('it-tasks/Section')
                ->where('section.slug', $slug)
                ->where('section.code', ItTask::SERVICE_PAGES[$slug])
                ->where('section.title', __("ui.service_pages.{$slug}.title"))
                ->has('section.offers'));
    }

    #[Test]
    public function страница_открывается_на_других_языках(): void
    {
        $this->get('/en/services/logistics')
            ->assertOk()
            ->assertSee('Logistics and transport');
    }

    #[Test]
    public function неизвестное_направление_404(): void
    {
        $this->get('/services/other')->assertNotFound();
        $this->get('/services/nope')->assertNotFound();
    }

    #[Test]
    public function на_странице_только_задачи_своего_направления(): void
    {
        $company = Company::factory()->create(['status' => Company::STATUS_ACTIVE]);
        $web = ItTask::factory()->create(['company_id' => $company->id, 'service_type' => 'web']);
        $bot = ItTask::factory()->create(['company_id' => $company->id, 'service_type' => 'automation']);
        ItTask::factory()->create(['company_id' => $company->id, 'service_type' => 'logistics']);
        ItTask::factory()->create([
            'company_id' => $company->id,
            'service_type' => 'web',
            'status' => ItTask::STATUS_CLOSED,
        ]);

        $this->get('/services/it')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('stats.active', 2)
            ->where('tasks', fn (Collection $tasks): bool => $tasks->pluck('slug')->sort()->values()->all()
                === collect([$web->slug, $bot->slug])->sort()->values()->all())
            // Виды IT — плитками со счётчиками
            ->where('kinds', fn (Collection $kinds): bool => $kinds->firstWhere('href', '/it-services?type=web')['count'] === 1)
            ->where('stats.resumes', null));
    }

    #[Test]
    public function исполнители_по_специализации(): void
    {
        $logist = Company::factory()->create([
            'status' => Company::STATUS_ACTIVE,
            'is_it_provider' => true,
            'it_specializations' => ['logistics'],
        ]);
        Company::factory()->create([
            'status' => Company::STATUS_ACTIVE,
            'is_it_provider' => true,
            'it_specializations' => ['web'],
        ]);
        // Специализация отмечена, но исполнителем компания не выступает
        Company::factory()->create([
            'status' => Company::STATUS_ACTIVE,
            'is_it_provider' => false,
            'it_specializations' => ['logistics'],
        ]);

        $this->get('/services/logistics')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('stats.providers', 1)
            ->has('providers', 1)
            ->where('providers.0.slug', $logist->slug));
    }

    #[Test]
    public function hr_показывает_подбор_персонала_и_резюме(): void
    {
        $company = Company::factory()->create(['status' => Company::STATUS_ACTIVE]);
        ItTask::factory()->create(['company_id' => $company->id, 'service_type' => 'hr']);
        $resume = $this->resume();

        $this->get('/services/hr')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('section.code', 'hr_services')
            ->where('stats.active', 1)
            ->where('stats.resumes', 1)
            ->has('resumes', 1)
            ->where('resumes.0.slug', $resume->slug)
            ->where('kinds.0.href', '/services/recruitment')
            ->where('kinds.0.count', 1)
            ->where('kinds.1.href', '/resumes'));

        $this->get('/services/recruitment')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('section.code', 'hr')
            ->where('stats.active', 1)
            ->has('resumes', 1)
            ->has('kinds', 0));
    }

    #[Test]
    public function страницы_направлений_в_карте_сайта(): void
    {
        $this->get('/sitemap-static.xml')
            ->assertOk()
            ->assertSee(url('/services/recruitment'), false);
    }

    private function resume(): Resume
    {
        $resume = new Resume([
            'title' => 'Менеджер по снабжению',
            'field' => 'procurement',
            'currency' => 'UZS',
            'employment' => ['full'],
            'jobs' => [],
            'contact_name' => 'Максуд Максудов',
        ]);
        $resume->user_id = User::factory()->create()->id;
        $resume->status = Resume::STATUS_PUBLISHED;
        $resume->published_at = now();
        $resume->experience_months = 0;
        $resume->save();
        $resume->slug = Resume::makeSlug($resume->title, $resume->id);
        $resume->saveQuietly();

        return $resume;
    }
}
