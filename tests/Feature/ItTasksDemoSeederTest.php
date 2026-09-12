<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Company;
use App\Models\ItTask;
use Database\Seeders\ItTasksDemoSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/** Демо-наполнение раздела «IT-услуги» — идемпотентно и видно на витрине. */
class ItTasksDemoSeederTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function сидер_создаёт_задачи_и_не_плодит_дублей(): void
    {
        $this->seed(ItTasksDemoSeeder::class);
        $this->seed(ItTasksDemoSeeder::class);

        $this->assertSame(12, ItTask::count());
        $this->assertSame(6, ItTask::active()->count());
        $this->assertSame(6, ItTask::completed()->count());
        $this->assertSame(3, Company::where('is_it_provider', true)->count());
        $this->assertSame(7, Company::where('source_note', 'like', 'Демонстрационная%')->count());
    }

    #[Test]
    public function выполненные_показываются_с_результатом_и_исполнителем(): void
    {
        $this->seed(ItTasksDemoSeeder::class);

        $this->get('/it-services')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('total', 6)
            ->where('tasks.data.0.completed', false));

        $this->get('/it-services?done=1')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('total', 6)
            ->where('filters.done', true)
            ->where('tasks.data.0.completed', true)
            ->where('tasks.data.0.result_url', 'https://andijan-yarn.uz')
            ->where('tasks.data.0.result_host', 'andijan-yarn.uz')
            ->where('tasks.data.0.contractor.name', 'IT-студия «Digital Plov»'));

        $done = ItTask::completed()->orderByDesc('completed_at')->first();

        // Выполненная задача открыта гостю — это портфолио раздела
        $this->get("/it-services/{$done->slug}")->assertOk()->assertInertia(fn (AssertableInertia $page) => $page
            ->where('task.completed', true)
            ->where('task.result_summary', $done->result_summary)
            ->where('task.contractor.slug', $done->contractor->slug));
    }

    #[Test]
    public function на_проде_сидер_отказывается(): void
    {
        app()->detectEnvironment(fn () => 'production');

        // Напрямую, без консольного вывода: command отсутствует
        (new ItTasksDemoSeeder)->run();

        $this->assertSame(0, ItTask::count());
    }
}
