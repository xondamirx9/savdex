<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Доступность публичных страниц и общая шапка.
 * Заменяет стандартную заглушку ExampleTest: та не использовала
 * RefreshDatabase и падала, как только главная стала ходить в базу.
 */
class PublicPagesTest extends TestCase
{
    use RefreshDatabase;

    /** @return array<string, array{string, string}> */
    public static function публичныеСтраницы(): array
    {
        return [
            'главная' => ['/', 'Home'],
            'о компании' => ['/about', 'About'],
            'новости' => ['/news', 'news/Index'],
            'тендеры' => ['/tenders', 'tenders/Index'],
            'тарифы' => ['/pricing', 'Pricing'],
            'каталог' => ['/catalog', 'catalog/Index'],
            'компании' => ['/companies', 'companies/Index'],
            'партнёры' => ['/partners', 'Partners'],
        ];
    }

    #[Test]
    #[DataProvider('публичныеСтраницы')]
    public function страница_открывается_гостю(string $url, string $component): void
    {
        $this->get($url)
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->component($component));
    }

    #[Test]
    #[DataProvider('публичныеСтраницы')]
    public function страница_открывается_и_авторизованному(string $url, string $component): void
    {
        $this->actingAs(User::factory()->create())
            ->get($url)
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->component($component));
    }

    /** Выдуманные цифры на витрине недопустимы — счётчики идут из базы. */
    #[Test]
    public function счётчики_на_главной_берутся_из_базы(): void
    {
        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page->where('stats.companies', 0));

        Company::factory()->count(3)->create(['status' => Company::STATUS_ACTIVE]);

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page->where('stats.companies', 3));
    }

    #[Test]
    public function общие_данные_шапки_доступны_на_каждой_странице(): void
    {
        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page
            ->has('auth')
            ->where('auth.user', null)
            ->has('locale'),
        );
    }
}
