<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Setting;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Юридические документы витрины.
 *
 * Публичная оферта — редакция юриста заказчика, поданная в банк-эквайер.
 * Тест сторожит две вещи, которые ломают проверку банка: пропавшие
 * разделы (страница обязана содержать документ целиком) и реквизиты,
 * разошедшиеся с офертой.
 */
class LegalDocumentsTest extends TestCase
{
    use RefreshDatabase;

    private function setting(string $key, mixed $value): void
    {
        Setting::updateOrCreate(
            ['key' => $key],
            ['group' => 'legal', 'label' => $key, 'type' => 'string', 'value' => $value],
        );
    }

    /** @return list<array{0: string}> */
    public static function documents(): array
    {
        return [['terms'], ['payment'], ['security'], ['privacy'], ['refunds']];
    }

    #[Test]
    #[DataProvider('documents')]
    public function документ_открывается_и_содержит_разделы(string $doc): void
    {
        $this->get("/{$doc}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('Legal')
                ->where('draft', false)
                ->has('blocks')
                // Каждый раздел — заголовок и хотя бы один узел содержимого:
                // пустой раздел на странице читается как обрыв документа
                ->has('blocks.0.heading')
                ->has('blocks.0.content')
            );
    }

    /** Оферта из 22 разделов: недостающий раздел — неполный договор. */
    #[Test]
    public function оферта_содержит_все_разделы_и_преамбулу(): void
    {
        $this->get('/terms')->assertInertia(fn (AssertableInertia $page) => $page
            ->has('blocks', 22)
            ->has('preamble', 2)
            ->where('blocks.0.heading', 'Общие положения')
            ->where('blocks.21.heading', 'Реквизиты SavdEx')
        );
    }

    /**
     * Нумерация пунктов внутри раздела обязана совпадать с номером
     * раздела: страница выводит номер раздела сама, и разъехавшаяся
     * нумерация означает, что раздел вставлен не на своё место.
     */
    #[Test]
    public function нумерация_пунктов_совпадает_с_номером_раздела(): void
    {
        $this->get('/terms')->assertInertia(function (AssertableInertia $page): void {
            $blocks = $page->toArray()['props']['blocks'];

            foreach ($blocks as $i => $block) {
                $number = $i + 1;

                foreach ($block['content'] as $node) {
                    if (! isset($node['p'])) {
                        continue;
                    }

                    // У раздела реквизитов пунктов нет — только список
                    $this->assertMatchesRegularExpression(
                        "/^{$number}\.\d+\. /u",
                        $node['p'],
                        "Пункт раздела «{$block['heading']}» пронумерован не по разделу",
                    );
                }
            }
        });
    }

    #[Test]
    public function реквизиты_в_оферте_приходят_из_настроек(): void
    {
        $this->setting('legal_full_name', '"TEST-GROUP" MCHJ');
        $this->setting('legal_tin', '123456789');
        $this->setting('legal_account', '20208000000000000001');
        $this->setting('legal_director', 'IVANOV IVAN');

        $this->get('/terms')->assertInertia(function (AssertableInertia $page): void {
            $requisites = $page->toArray()['props']['blocks'][21]['content'][0]['list'];

            $this->assertContains('"TEST-GROUP" MCHJ', $requisites);
            $this->assertContains('ИНН: 123456789', $requisites);
            $this->assertContains('Расчётный счёт: 20208000000000000001', $requisites);
            $this->assertContains('Руководитель: IVANOV IVAN', $requisites);
        });
    }

    /** Пустая настройка не должна давать строку «Телефон: » без значения. */
    #[Test]
    public function незаполненный_реквизит_не_показывается(): void
    {
        $this->setting('legal_phone', '');
        $this->setting('legal_email', '');

        $this->get('/terms')->assertInertia(function (AssertableInertia $page): void {
            $requisites = $page->toArray()['props']['blocks'][21]['content'][0]['list'];

            foreach ($requisites as $line) {
                $this->assertStringNotContainsString('Телефон: ', $line);
                $this->assertStringNotContainsString('E-mail: ', $line);
            }
        });
    }

    /**
     * В тексте оферты — полное наименование: в исходнике на этих местах
     * стоит «[полное наименование юридического лица]», и краткая форма
     * разошлась бы с разделом реквизитов той же страницы.
     */
    #[Test]
    public function в_текст_оферты_подставляется_полное_наименование(): void
    {
        $this->setting('legal_full_name', '"PROVERKA" MCHJ');
        $this->setting('legal_name', 'ООО «ПРОВЕРКА»');

        $this->get('/terms')->assertInertia(function (AssertableInertia $page): void {
            $props = $page->toArray()['props'];

            $this->assertStringContainsString('"PROVERKA" MCHJ', $props['preamble'][0]);
            $this->assertStringContainsString('"PROVERKA" MCHJ', $props['blocks'][0]['content'][0]['p']);
            $this->assertStringContainsString('"PROVERKA" MCHJ', $props['blocks'][21]['content'][0]['list'][0]);
        });
    }

    /** Пока полное наименование не заполнено, в тексте краткое. */
    #[Test]
    public function без_полного_наименования_в_тексте_краткое(): void
    {
        $this->setting('legal_full_name', '');
        $this->setting('legal_name', 'ООО «ПРОВЕРКА»');

        $this->get('/terms')->assertInertia(function (AssertableInertia $page): void {
            $props = $page->toArray()['props'];

            $this->assertStringContainsString('ООО «ПРОВЕРКА»', $props['preamble'][0]);
            $this->assertStringContainsString('ООО «ПРОВЕРКА»', $props['blocks'][0]['content'][0]['p']);
        });
    }

    /**
     * Политика возвратов подчинена разделу 14 оферты: два документа
     * на одном сайте, обещающие разное, — спор с клиентом, в котором
     * площадка заведомо неправа.
     */
    #[Test]
    public function политика_возвратов_не_противоречит_оферте(): void
    {
        $this->get('/refunds')->assertInertia(function (AssertableInertia $page): void {
            $text = json_encode($page->toArray()['props']['blocks'], JSON_UNESCAPED_UNICODE);

            // Прежняя редакция обещала возврат за неиспользованный доступ —
            // ровно то основание, которое пункты 14.2 и 14.3 оферты отклоняют
            $this->assertStringNotContainsString('в течение 14 дней с момента списания', $text);
            $this->assertStringNotContainsString('20 % месячного лимита', $text);
            $this->assertStringContainsString('14.2', $text);
        });
    }

    #[Test]
    public function неизвестный_документ_отдаёт_404(): void
    {
        $this->get('/dogovor')->assertNotFound();
    }
}
