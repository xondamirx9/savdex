<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\CompanyDocument;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Файлы компании: презентации, прайсы и документы для верификации.
 *
 * Ключевое здесь — доступ. Файл лежит в приватном хранилище и отдаётся
 * контроллером: положить его в public/ значит обойти и модерацию,
 * и флаг публичности — достаточно угадать имя.
 */
class CompanyFileTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    private User $user;

    protected function setUp(): void
    {
        parent::setUp();

        Storage::fake('local');

        $this->company = Company::factory()->create();
        $this->user = User::factory()->create(['company_id' => $this->company->id]);
    }

    #[Test]
    public function материал_загружается_и_сразу_виден(): void
    {
        $this->actingAs($this->user)
            ->post('/cabinet/company/files', [
                'type' => 'price_list',
                'title' => 'Прайс-лист на цемент, июль',
                'file' => UploadedFile::fake()->create('price.pdf', 120, 'application/pdf'),
                'is_public' => true,
            ])
            ->assertSessionHas('success');

        $document = CompanyDocument::first();

        $this->assertNotNull($document);
        $this->assertTrue($document->isMaterial());

        // Материалу модерация не нужна: это не подтверждение статуса
        $this->assertSame(CompanyDocument::STATUS_APPROVED, $document->moderation_status);
        $this->assertTrue($document->isVisibleOnCard());

        Storage::disk('local')->assertExists($document->file_path);
    }

    /**
     * MIME файлов Office длиннее 64 символов — колонка была уже,
     * и Postgres ронял загрузку презентаций ошибкой 500.
     */
    #[Test]
    public function презентация_с_длинным_mime_загружается(): void
    {
        $mime = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';

        $this->actingAs($this->user)
            ->post('/cabinet/company/files', [
                'type' => 'presentation',
                'title' => 'Презентация компании',
                'file' => UploadedFile::fake()->create('deck.pptx', 500, $mime),
                'is_public' => true,
            ])
            ->assertSessionHasNoErrors()
            ->assertSessionHas('success');

        $this->assertSame($mime, CompanyDocument::firstOrFail()->mime);
    }

    /**
     * Запись, чей файл стёрт деплоем эфемерного хранилища, в кабинете
     * помечается — владелец видит, что загрузку нужно повторить.
     */
    #[Test]
    public function пропавший_файл_помечается_в_кабинете(): void
    {
        Storage::disk('local')->put('company-files/alive.pdf', 'pdf');

        CompanyDocument::create([
            'company_id' => $this->company->id,
            'type' => 'price_list',
            'title' => 'Живой файл',
            'file_path' => 'company-files/alive.pdf',
            'is_public' => true,
        ])->forceFill(['created_at' => now()->subMinute()])->save();

        CompanyDocument::create([
            'company_id' => $this->company->id,
            'type' => 'other',
            'title' => 'Пропавший файл',
            'file_path' => 'company-files/lost.jpg',
            'is_public' => true,
        ]);

        $this->actingAs($this->user)->get('/cabinet/company')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('documents.0.missing', true)   // latest() — пропавший первым
                ->where('documents.1.missing', false));
    }

    #[Test]
    public function документ_уходит_на_проверку_и_до_неё_не_виден(): void
    {
        $this->actingAs($this->user)->post('/cabinet/company/files', [
            'type' => 'license',
            'title' => 'Лицензия на перевозки',
            'file' => UploadedFile::fake()->create('license.pdf', 90, 'application/pdf'),
            'is_public' => true,
        ]);

        $document = CompanyDocument::first();

        $this->assertSame(CompanyDocument::STATUS_PENDING, $document->moderation_status);

        // Показывать непроверенную лицензию значит выдавать компании
        // подтверждение, которого она не получала
        $this->assertFalse($document->isVisibleOnCard());
    }

    #[Test]
    public function исполняемый_файл_отклоняется(): void
    {
        $this->actingAs($this->user)
            ->post('/cabinet/company/files', [
                'type' => 'presentation',
                'title' => 'Презентация',
                'file' => UploadedFile::fake()->create('virus.exe', 10),
            ])
            ->assertSessionHasErrors('file');

        $this->assertSame(0, CompanyDocument::count());
    }

    #[Test]
    public function просроченный_срок_действия_отклоняется(): void
    {
        $this->actingAs($this->user)
            ->post('/cabinet/company/files', [
                'type' => 'certificate',
                'title' => 'Сертификат',
                'file' => UploadedFile::fake()->create('cert.pdf', 50, 'application/pdf'),
                'valid_until' => now()->subDay()->toDateString(),
            ])
            ->assertSessionHasErrors('valid_until');
    }

    #[Test]
    public function показ_на_визитке_переключается(): void
    {
        $document = $this->makeMaterial();

        $this->actingAs($this->user)
            ->patch("/cabinet/company/files/{$document->id}", ['is_public' => false])
            ->assertSessionHas('success');

        $this->assertFalse($document->fresh()->is_public);
        $this->assertFalse($document->fresh()->isVisibleOnCard());
    }

    #[Test]
    public function публичный_материал_скачивает_любой(): void
    {
        $document = $this->makeMaterial();

        $this->get("/files/{$document->id}")->assertOk();
    }

    #[Test]
    public function скрытый_файл_чужому_не_отдаётся(): void
    {
        $document = $this->makeMaterial(['is_public' => false]);

        $this->get("/files/{$document->id}")->assertNotFound();

        // Своим сотрудникам — отдаётся: это их файл
        $this->actingAs($this->user)->get("/files/{$document->id}")->assertOk();
    }

    #[Test]
    public function непроверенный_документ_чужому_не_отдаётся(): void
    {
        $document = $this->makeMaterial([
            'type' => 'license',
            'moderation_status' => CompanyDocument::STATUS_PENDING,
        ]);

        $this->get("/files/{$document->id}")->assertNotFound();
    }

    #[Test]
    public function чужой_файл_нельзя_удалить(): void
    {
        $document = $this->makeMaterial();
        $stranger = User::factory()->create(['company_id' => Company::factory()->create()->id]);

        $this->actingAs($stranger)
            ->delete("/cabinet/company/files/{$document->id}")
            ->assertNotFound();

        $this->assertSame(1, CompanyDocument::count());
    }

    #[Test]
    public function удаление_убирает_файл_с_диска(): void
    {
        $document = $this->makeMaterial();
        $path = $document->file_path;

        $this->actingAs($this->user)->delete("/cabinet/company/files/{$document->id}");

        $this->assertSame(0, CompanyDocument::count());
        Storage::disk('local')->assertMissing($path);
    }

    /**
     * Проверяем через props, а не assertSee: Inertia отдаёт данные
     * JSON-строкой внутри data-page, и кириллица там экранирована
     * как \uXXXX — поиск по HTML такой текст не найдёт.
     */
    #[Test]
    public function файлы_показываются_на_визитке(): void
    {
        $this->makeMaterial(['title' => 'Каталог продукции 2026']);
        $this->makeMaterial(['title' => 'Внутренний регламент', 'is_public' => false]);

        $this->get("/company/{$this->company->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('files', 1)
                ->where('files.0.title', 'Каталог продукции 2026'),
            );
    }

    /** @param array<string, mixed> $overrides */
    private function makeMaterial(array $overrides = []): CompanyDocument
    {
        $path = UploadedFile::fake()
            ->create('file.pdf', 40, 'application/pdf')
            ->store("companies/{$this->company->id}/documents", 'local');

        return CompanyDocument::create([
            'company_id' => $this->company->id,
            'type' => 'presentation',
            'title' => 'Презентация компании',
            'file_path' => $path,
            'file_size' => 40960,
            'mime' => 'application/pdf',
            'is_public' => true,
            'moderation_status' => CompanyDocument::STATUS_APPROVED,
            ...$overrides,
        ]);
    }
}
