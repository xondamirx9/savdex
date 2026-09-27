<?php

declare(strict_types=1);

namespace Tests\Unit;

use App\Support\PageBody;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\TestCase;

/** Разметка текста страницы из админки (App\Support\PageBody). */
class PageBodyTest extends TestCase
{
    #[Test]
    public function пометки_превращаются_в_блоки(): void
    {
        $text = "## Если вы поставщик\n\n"
            ."1. Зарегистрируйтесь.\nДо подтверждения публиковать нельзя.\n2. Заполните карточку.\n\n"
            ."! Контакты в тексте запрещены.\nОни скрываются автоматически.\n\n"
            ."- Достоверные реквизиты\n- Подходящая категория\n\n"
            ."Обычный абзац\nв две строки.";

        $this->assertSame([
            ['type' => 'heading', 'text' => 'Если вы поставщик'],
            ['type' => 'steps', 'items' => [
                ['title' => 'Зарегистрируйтесь.', 'hint' => 'До подтверждения публиковать нельзя.'],
                ['title' => 'Заполните карточку.', 'hint' => ''],
            ]],
            ['type' => 'note', 'title' => 'Контакты в тексте запрещены.', 'text' => 'Они скрываются автоматически.'],
            ['type' => 'list', 'items' => ['Достоверные реквизиты', 'Подходящая категория']],
            ['type' => 'text', 'text' => 'Обычный абзац в две строки.'],
        ], PageBody::blocks($text));
    }

    #[Test]
    public function пустой_текст_и_лишние_пустые_строки(): void
    {
        $this->assertSame([], PageBody::blocks(null));
        $this->assertSame([], PageBody::blocks("  \n\n "));
        // Windows-переводы строк из формы и строка из пробелов между абзацами
        $this->assertCount(2, PageBody::blocks("Первый\r\n   \r\nВторой"));
    }

    #[Test]
    public function перевод_не_трогает_разметку(): void
    {
        $blocks = PageBody::blocks("## Шаги\n\n1. Раз\nПодсказка");

        $this->assertSame(['Шаги', 'Раз', 'Подсказка'], PageBody::strings($blocks));
        $this->assertSame([
            ['type' => 'heading', 'text' => '[Шаги]'],
            ['type' => 'steps', 'items' => [['title' => '[Раз]', 'hint' => '[Подсказка]']]],
        ], PageBody::map($blocks, fn (string $s): string => "[{$s}]"));
    }
}
