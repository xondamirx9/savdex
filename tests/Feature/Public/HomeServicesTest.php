<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\ItTask;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Две популярные услуги в плитке «Популярные категории» на главной.
 *
 * Направления «Доп. услуг» ранжируются по числу активных задач;
 * пока задач нет, показываются IT-услуги и логистика.
 */
class HomeServicesTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function без_задач_показаны_услуги_по_умолчанию(): void
    {
        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page
            ->has('services', 2)
            ->where('services.0.type', 'it')
            ->where('services.1.type', 'logistics'));
    }

    #[Test]
    public function выше_направления_с_большим_числом_задач(): void
    {
        $company = Company::factory()->create(['status' => Company::STATUS_ACTIVE]);

        ItTask::factory()->count(3)->create(['company_id' => $company->id, 'service_type' => 'accounting']);
        ItTask::factory()->count(2)->create(['company_id' => $company->id, 'service_type' => 'hr']);
        // Виды IT-услуг складываются в одно направление
        ItTask::factory()->create(['company_id' => $company->id, 'service_type' => 'web']);
        // «Другое» в плитку не попадает, закрытые задачи не считаются
        ItTask::factory()->count(5)->create(['company_id' => $company->id, 'service_type' => 'other']);
        ItTask::factory()->count(5)->create([
            'company_id' => $company->id,
            'service_type' => 'customs',
            'status' => ItTask::STATUS_CLOSED,
        ]);

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page
            ->has('services', 2)
            ->where('services.0.type', 'accounting')
            ->where('services.0.tasks', 3)
            ->where('services.1.type', 'hr')
            ->where('services.1.tasks', 2));
    }
}
