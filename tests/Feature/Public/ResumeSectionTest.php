<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\City;
use App\Models\Country;
use App\Models\Resume;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Раздел «Резюме» — кого можно нанять.
 *
 * Бесплатный с обеих сторон: соискатель публикует без оплаты,
 * компания смотрит без списания кредитов. Контакты открыты вошедшим:
 * телефон живого человека не для анонимов и поисковых роботов.
 */
class ResumeSectionTest extends TestCase
{
    use RefreshDatabase;

    /** @param array<string, mixed> $overrides */
    private function resume(array $overrides = []): Resume
    {
        $user = User::factory()->create();

        $status = $overrides['status'] ?? Resume::STATUS_PUBLISHED;
        unset($overrides['status']);

        $resume = new Resume([
            'title' => 'Менеджер по снабжению',
            'field' => 'procurement',
            'salary' => 8_000_000,
            'currency' => 'UZS',
            'employment' => ['full'],
            'schedule' => ['full_day'],
            'about' => 'Семь лет в закупках стройматериалов.',
            'skills' => ['1C', 'Переговоры'],
            'jobs' => [['company' => 'ООО «Стройбаза»', 'position' => 'Снабженец', 'start' => '2019-01', 'end' => '2023-01', 'duties' => '']],
            'contact_name' => 'Максуд Максудов',
            'contact_phone' => '+998 90 777-88-99',
            'contact_email' => 'maksud@example.com',
            'show_phone' => true,
            'show_email' => true,
            ...$overrides,
        ]);

        $resume->user_id = $user->id;
        $resume->status = $status;
        $resume->published_at = now();
        $resume->experience_months = Resume::experienceMonths($resume->jobs);
        $resume->save();
        $resume->slug = Resume::makeSlug($resume->title, $resume->id);
        $resume->saveQuietly();

        return $resume;
    }

    #[Test]
    public function в_разделе_видно_только_опубликованные(): void
    {
        $published = $this->resume();
        $this->resume(['title' => 'Черновик', 'status' => Resume::STATUS_DRAFT]);
        $this->resume(['title' => 'Снятое', 'status' => Resume::STATUS_HIDDEN]);

        $this->get('/resumes')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('resumes/Index')
                ->where('total', 1)
                ->where('resumes.data.0.slug', $published->slug)
                ->where('resumes.data.0.experience.years', 4));
    }

    #[Test]
    public function поиск_и_фильтры_работают(): void
    {
        $this->resume(['title' => 'Менеджер по снабжению', 'field' => 'procurement']);
        $this->resume(['title' => 'Водитель-экспедитор', 'field' => 'logistics', 'jobs' => []]);

        $this->get('/resumes?q=снабжен')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('total', 1));

        $this->get('/resumes?field=logistics')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('total', 1)
                ->where('resumes.data.0.title', 'Водитель-экспедитор'));

        // Опыт от трёх лет: у водителя мест работы нет вовсе
        $this->get('/resumes?experience=from3')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('total', 1)
                ->where('resumes.data.0.title', 'Менеджер по снабжению'));
    }

    #[Test]
    public function фильтр_по_городу_показывает_только_занятые_города(): void
    {
        $country = Country::create(['code' => 'uz', 'phone_code' => '+998', 'currency_code' => 'UZS', 'is_active' => true]);
        $tashkent = City::create(['country_id' => $country->id, 'slug' => 'tashkent', 'is_active' => true]);
        $tashkent->translations()->create(['locale' => 'ru', 'name' => 'Ташкент']);
        $samarkand = City::create(['country_id' => $country->id, 'slug' => 'samarkand', 'is_active' => true]);
        $samarkand->translations()->create(['locale' => 'ru', 'name' => 'Самарканд']);

        $this->resume(['city_id' => $tashkent->id, 'country_id' => $country->id]);

        $this->get('/resumes')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('cities', 1)
                ->where('cities.0.name', 'Ташкент'));

        $this->get('/resumes?city='.$samarkand->id)
            ->assertInertia(fn (AssertableInertia $page) => $page->where('total', 0));
    }

    /** Телефон живого человека не отдаём анониму и поисковому роботу. */
    #[Test]
    public function контакты_видны_только_вошедшим(): void
    {
        $resume = $this->resume();

        $this->get('/resume/'.$resume->slug)
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('resumes/Show')
                ->where('resume.title', 'Менеджер по снабжению')
                ->where('resume.contacts', null))
            ->assertDontSee('777-88-99', false);

        $this->actingAs(User::factory()->create())
            ->get('/resume/'.$resume->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('resume.contacts.phone', '+998 90 777-88-99')
                ->where('resume.contacts.email', 'maksud@example.com'));
    }

    /** Что показывать, решает соискатель. */
    #[Test]
    public function скрытый_телефон_не_показывается_даже_вошедшим(): void
    {
        $resume = $this->resume(['show_phone' => false]);

        $this->actingAs(User::factory()->create())
            ->get('/resume/'.$resume->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->missing('resume.contacts.phone')
                ->where('resume.contacts.email', 'maksud@example.com'));
    }

    #[Test]
    public function черновик_по_прямой_ссылке_не_открывается(): void
    {
        $draft = $this->resume(['status' => Resume::STATUS_DRAFT]);

        $this->get('/resume/'.$draft->slug)->assertNotFound();
    }

    #[Test]
    public function просмотры_считаются_кроме_своих(): void
    {
        $resume = $this->resume();

        $this->get('/resume/'.$resume->slug);
        $this->assertSame(1, $resume->fresh()->views_count);

        $this->actingAs(User::find($resume->user_id))->get('/resume/'.$resume->slug);
        $this->assertSame(1, $resume->fresh()->views_count);
    }

    #[Test]
    public function похожие_подбираются_по_сфере(): void
    {
        $resume = $this->resume();
        $this->resume(['title' => 'Специалист по закупкам', 'field' => 'procurement']);
        $this->resume(['title' => 'Водитель', 'field' => 'logistics']);

        $this->get('/resume/'.$resume->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('similar', 1)
                ->where('similar.0.title', 'Специалист по закупкам'));
    }
}
