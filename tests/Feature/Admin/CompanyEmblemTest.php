<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Company;
use App\Support\CompanyEmblem;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Storage;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Эмблемы компаний: плашка с инициалами вместо чужого логотипа.
 *
 * Настоящие знаки площадка использовать не может — авторское право.
 * Эмблема обязана быть стабильной (одна компания — один цвет),
 * нести инициалы и вставать обычным логотипом, чтобы показываться
 * везде без отдельного кода.
 */
class CompanyEmblemTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function эмблема_становится_логотипом_и_несёт_инициалы(): void
    {
        Storage::fake('public');

        $company = Company::factory()->create([
            'name' => 'Samarqand Fruit Export',
            'logo_path' => null,
            'city_id' => null,
            'address' => null,
        ]);

        CompanyEmblem::assign($company);

        $company->refresh();

        $this->assertNotNull($company->logo_path);
        Storage::disk('public')->assertExists($company->logo_path);

        $svg = Storage::disk('public')->get($company->logo_path);

        $this->assertStringStartsWith('<svg', $svg);
        $this->assertStringContainsString('>SF</text>', $svg);
        // Компания самаркандская — палитра своего региона
        $this->assertStringContainsString('#1d5f9e', $svg);

        // Логотип отдаётся витрине обычным путём
        $this->assertNotNull($company->logoUrl());
    }

    /** Один и тот же цвет при каждой генерации — без региона тоже. */
    #[Test]
    public function цвет_стабилен_между_генерациями(): void
    {
        Storage::fake('public');

        $company = Company::factory()->create(['name' => 'No Region Trading', 'address' => null, 'city_id' => null]);

        CompanyEmblem::assign($company);
        $first = Storage::disk('public')->get($company->fresh()->logo_path);

        CompanyEmblem::assign($company->fresh());
        $second = Storage::disk('public')->get($company->fresh()->logo_path);

        $this->assertSame($first, $second);
    }
}
