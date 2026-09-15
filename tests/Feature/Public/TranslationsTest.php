<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Http\Middleware\HandleInertiaRequests;
use App\Support\Locales;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Request;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Словарь интерфейса.
 *
 * Проверяется не наличие файлов, а то, что перевод доезжает до
 * страницы на нужном языке и что ни один ключ не потерялся:
 * пропущенный ключ выглядит на экране как «nav.catalog» — заметно
 * посетителю и стыдно.
 */
class TranslationsTest extends TestCase
{
    use RefreshDatabase;

    /** @return list<array{string}> */
    public static function языки(): array
    {
        return array_map(fn (string $code): array => [$code], Locales::codes());
    }

    #[Test]
    #[DataProvider('языки')]
    public function словарь_приходит_на_странице(string $locale): void
    {
        $this->get(Locales::url('/', $locale))
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('locale', $locale)
                ->has('translations.nav.catalog')
                ->has('translations.home.h1'));
    }

    /**
     * Переходы Inertia словарь не тянут.
     *
     * Полторы тысячи фраз на каждый клик — это чужой мобильный
     * трафик. У браузера словарь уже есть с первой загрузки.
     */
    #[Test]
    public function переход_внутри_приложения_словарь_не_повторяет(): void
    {
        $middleware = new HandleInertiaRequests;

        // Сессия нужна: общие пропсы читают из неё флеш-сообщения
        $full = tap(Request::create('/catalog'), fn (Request $r) => $r->setLaravelSession(session()->driver()));
        $inertia = tap(Request::create('/catalog'), fn (Request $r) => $r->setLaravelSession(session()->driver()));
        $inertia->headers->set('X-Inertia', 'true');

        $this->assertIsArray($middleware->share($full)['translations']);
        $this->assertNull($middleware->share($inertia)['translations']);
    }

    /**
     * Непереведённый ключ показывает русский текст, а не сам ключ.
     *
     * Словарь растёт разделами: сначала русский, потом остальные
     * четыре. В этот промежуток t() без подложки выводил бы на экран
     * «cabinet.dashboard.title» — техническую строку вместо заголовка.
     */
    #[Test]
    public function непереведённый_ключ_подменяется_русским(): void
    {
        app()->setLocale('en');

        // Ключ, которого в английском словаре заведомо нет
        app('translator')->addLines(['ui.probe.only_russian' => 'Только по-русски'], Locales::DEFAULT);

        $request = tap(Request::create('/'), fn (Request $r) => $r->setLaravelSession(session()->driver()));
        $translations = (new HandleInertiaRequests)->share($request)['translations'];

        $this->assertSame('Только по-русски', $translations['probe']['only_russian']);

        // Подложка не затирает то, что переведено
        $this->assertSame(
            __('ui.nav.catalog', locale: 'en'),
            $translations['nav']['catalog'],
        );
    }

    /**
     * Полнота перевода.
     *
     * Ключи сверяются с русским — исходным языком. Расхождение
     * значит либо непереведённую фразу, либо забытый при правке
     * ключ, который останется в словаре навсегда.
     */
    #[Test]
    #[DataProvider('языки')]
    public function все_ключи_переведены(string $locale): void
    {
        $source = $this->flatten(require lang_path('ru/ui.php'));
        $target = $this->flatten(require lang_path("{$locale}/ui.php"));

        $missing = array_diff(array_keys($source), array_keys($target));
        $extra = array_diff(array_keys($target), array_keys($source));

        $this->assertSame([], array_values($missing), "Нет перевода: {$locale}");
        $this->assertSame([], array_values($extra), "Лишние ключи: {$locale}");
    }

    /**
     * Каждый ключ, который спрашивает интерфейс, есть в словаре.
     *
     * t() возвращает пропущенный ключ как есть, и на экран выходит
     * «cabinet.billing.title» вместо заголовка. Найти это глазами
     * можно только обойдя весь кабинет на пяти языках, поэтому
     * ключи собираются из исходников и сверяются со словарём.
     *
     * Вычисляемые ключи (t(`...${x}`)) сюда не попадают: их значение
     * известно только в браузере.
     */
    #[Test]
    public function все_ключи_из_интерфейса_есть_в_словаре(): void
    {
        $dictionary = $this->flatten(require lang_path('ru/ui.php'));
        $missing = [];

        $files = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator(resource_path('js'), \FilesystemIterator::SKIP_DOTS),
        );

        foreach ($files as $file) {
            if (! in_array($file->getExtension(), ['ts', 'tsx'], true)) {
                continue;
            }

            preg_match_all(
                "/\bt(?:Choice)?\('([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)'/",
                (string) file_get_contents($file->getPathname()),
                $found,
            );

            foreach ($found[1] as $key) {
                if (! array_key_exists($key, $dictionary)) {
                    $missing[$key] = $file->getFilename();
                }
            }
        }

        // Путь к файлу в сообщении: иначе ключ приходится искать
        // поиском по всему фронтенду
        $this->assertSame([], $missing, 'Ключи без перевода');
    }

    /**
     * Ни одна фраза не осталась русской в чужом словаре.
     *
     * Самая частая ошибка при переводе — скопировать файл и забыть
     * часть строк. Кириллица в узбекском латинском, английском,
     * китайском и турецком словаре — верный признак именно этого.
     */
    #[Test]
    #[DataProvider('языки')]
    public function в_переводе_не_осталось_русского(string $locale): void
    {
        if ($locale === Locales::DEFAULT) {
            $this->markTestSkipped('Русский — исходный язык');
        }

        $untranslated = array_filter(
            $this->flatten(require lang_path("{$locale}/ui.php")),
            fn (string $text): bool => preg_match('/[А-Яа-яЁё]/u', $text) === 1,
        );

        $this->assertSame([], array_keys($untranslated), "Русский текст в словаре {$locale}");
    }

    /**
     * Подстановки должны совпадать.
     *
     * Потерянное «:count» в переводе — это «объявлений» без числа,
     * а лишнее — незаменённое двоеточие прямо на экране.
     */
    #[Test]
    #[DataProvider('языки')]
    public function подстановки_сохранены(string $locale): void
    {
        $source = $this->flatten(require lang_path('ru/ui.php'));
        $target = $this->flatten(require lang_path("{$locale}/ui.php"));

        foreach ($source as $key => $text) {
            // Сравниваются имена, а не число вхождений: у русского
            // три формы после числа, у турецкого одна — и «:count»
            // встречается разное количество раз совершенно законно
            $this->assertSame(
                $this->placeholders($text),
                $this->placeholders($target[$key] ?? ''),
                "Подстановки разошлись: {$locale}, ключ {$key}",
            );
        }
    }

    /** @return list<string> */
    private function placeholders(string $text): array
    {
        preg_match_all('/:([a-z_]+)/', $text, $found);

        $names = array_values(array_unique($found[1]));
        sort($names);

        return $names;
    }

    /**
     * @param  array<string, mixed>  $items
     * @return array<string, string>
     */
    private function flatten(array $items, string $prefix = ''): array
    {
        $flat = [];

        foreach ($items as $key => $value) {
            $path = $prefix === '' ? (string) $key : "{$prefix}.{$key}";

            if (is_array($value)) {
                $flat += $this->flatten($value, $path);

                continue;
            }

            $flat[$path] = (string) $value;
        }

        return $flat;
    }
}
