<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Country;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Collection;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Фильтры каталога компаний не заводят в тупик.
 *
 * Справочник держит три десятка стран, а компании пока в немногих.
 * Список стран прямо из справочника обещал венгерские компании
 * и открывал «по вашему запросу ничего нет» — и так на каждой второй
 * стране подряд, отчего каталог выглядел сломанным.
 *
 * Правило одно на все фильтры: вариант предлагается, только если
 * за ним кто-то есть, и рядом стоит число. Считается оно с учётом
 * остальных выбранных фильтров — иначе цифра рядом со страной
 * обещала бы компании, которых при выбранном типе не существует.
 */
class CompanyFilterFacetsTest extends TestCase
{
    use RefreshDatabase;

    private function country(string $code, string $name): Country
    {
        $country = Country::firstOrCreate(
            ['code' => $code],
            ['phone_code' => '000', 'currency_code' => 'USD', 'is_active' => true],
        );

        $country->translations()->firstOrCreate(['locale' => 'ru'], ['name' => $name]);

        return $country;
    }

    /** @param array<string, mixed> $overrides */
    private function company(Country $country, array $overrides = []): Company
    {
        return Company::factory()->create([
            'country_id' => $country->id,
            'type' => 'manufacturer',
            'status' => Company::STATUS_ACTIVE,
            ...$overrides,
        ]);
    }

    #[Test]
    public function страна_без_компаний_в_фильтре_не_предлагается(): void
    {
        $uz = $this->country('uz', 'Узбекистан');
        $this->country('hu', 'Венгрия');

        $this->company($uz);
        $this->company($uz);

        $this->get('/companies')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('countries', fn (Collection $countries): bool => $countries->pluck('code')->all() === ['uz'])
                ->where('countries.0.count', 2));
    }

    #[Test]
    public function число_рядом_со_страной_учитывает_остальные_фильтры(): void
    {
        $uz = $this->country('uz', 'Узбекистан');
        $kz = $this->country('kz', 'Казахстан');

        $this->company($uz, ['type' => 'manufacturer']);
        $this->company($uz, ['type' => 'service']);
        $this->company($kz, ['type' => 'service']);

        // Без фильтра по типу — обе страны со своими числами.
        // Порядок в списке значимый: внутри одного sort — по алфавиту
        // языка страницы, поэтому Казахстан стоит выше Узбекистана
        $this->get('/companies')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('countries', fn (Collection $countries): bool => $countries
                    ->pluck('count', 'code')
                    ->all() === ['kz' => 1, 'uz' => 2]));

        // С фильтром «производитель» Казахстана в списке нет: там
        // производителей ноль, и переключатель открыл бы пустую страницу
        $this->get('/companies?type=manufacturer')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('companies.data', 1)
                ->where('countries', fn (Collection $countries): bool => $countries
                    ->pluck('count', 'code')
                    ->all() === ['uz' => 1]));
    }

    /**
     * Выбранная страна остаётся в списке, даже опустев.
     *
     * Ссылку на страну присылают и сохраняют в закладки, а компании
     * с площадки уходят. Пропади переключатель — он остался бы нажатым,
     * и вернуть его в «Все страны» было бы нечем.
     */
    #[Test]
    public function выбранный_вариант_из_списка_не_пропадает(): void
    {
        $uz = $this->country('uz', 'Узбекистан');
        $this->country('hu', 'Венгрия');
        $this->company($uz);

        $this->get('/companies?country=hu')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('companies.data', 0)
                ->where('countries', fn (Collection $countries): bool => $countries
                    ->pluck('count', 'code')
                    ->all() === ['hu' => 0, 'uz' => 1]));
    }

    #[Test]
    public function пустые_типы_возрасты_и_проверка_не_предлагаются(): void
    {
        $uz = $this->country('uz', 'Узбекистан');

        $this->company($uz, ['type' => 'manufacturer', 'created_at' => now()->subYears(7)]);

        $this->get('/companies')
            ->assertInertia(fn (AssertableInertia $page) => $page
                // В справочнике типов пять строк, компании есть у одного
                ->where('types', fn (Collection $types): bool => $types
                    ->pluck('count', 'value')
                    ->all() === ['manufacturer' => 1])
                // Возраст: только «более пяти лет»
                ->where('facets.ages', ['lt1' => 0, '1to5' => 0, 'gt5' => 1])
                // Проверенных нет — блок «Надёжность» прятать
                ->where('facets.verified', 0));
    }

    #[Test]
    public function проверенные_считаются_под_текущими_фильтрами(): void
    {
        $uz = $this->country('uz', 'Узбекистан');
        $kz = $this->country('kz', 'Казахстан');

        $this->company($uz, ['verification_level' => Company::VERIFICATION_COMPANY]);
        $this->company($uz);
        $this->company($kz, ['verification_level' => Company::VERIFICATION_COMPANY]);

        $this->get('/companies?country=uz')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('facets.verified', 1));

        // Свой же фильтр при подсчёте не учитывается: иначе число
        // рядом с галочкой менялось бы от нажатия на неё саму
        $this->get('/companies?country=uz&verified=1')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('companies.data', 1)
                ->where('facets.verified', 1));
    }

    #[Test]
    public function фильтр_по_стране_отбирает_компании(): void
    {
        $uz = $this->country('uz', 'Узбекистан');
        $kz = $this->country('kz', 'Казахстан');

        $this->company($uz, ['name' => 'ООО «Ташкентский кирпич»']);
        $this->company($kz);

        $this->get('/companies?country=uz')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('companies.data', 1)
                ->where('companies.data.0.name', 'ООО «Ташкентский кирпич»'));

        // Регистр кода из адреса значения не имеет
        $this->get('/companies?country=UZ')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('companies.data', 1));
    }
}
