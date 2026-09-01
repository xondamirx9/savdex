<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Пометка об источнике данных на визитке.
 *
 * Карточки, заведённые площадкой из открытых источников, обязаны
 * говорить об этом; рядом — кнопка на сайт компании. Текст и сайт
 * правятся в админке; пустая пометка скрывает блок.
 */
class CompanySourceNoteTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function визитка_отдаёт_пометку_и_сайт_кнопкой(): void
    {
        $company = Company::factory()->create([
            'source_note' => 'Данные компании взяты из открытых источников.',
            'website' => 'oscar-travel.uz',
        ]);

        $this->get('/company/'.$company->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('company.source_note', 'Данные компании взяты из открытых источников.')
                // Сайт нормализуется до кликабельной ссылки
                ->where('company.website', 'https://oscar-travel.uz'));
    }

    #[Test]
    public function без_пометки_блок_скрыт(): void
    {
        $company = Company::factory()->create(['source_note' => null]);

        $this->get('/company/'.$company->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('company.source_note', null));
    }
}
