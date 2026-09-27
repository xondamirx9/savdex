<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Setting;
use App\Support\Seo;
use Inertia\Inertia;
use Inertia\Response;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;

/**
 * Юридические документы площадки.
 *
 * Текст оферты — редакция, подготовленная юристом заказчика; менять
 * формулировки при правках кода нельзя. Наименование оператора и
 * реквизиты подставляются из настроек админки: смена банка или адреса
 * не должна требовать деплоя.
 *
 * Состав и подробность разделов про оплату продиктованы проверкой ДИБ
 * Antifraud банка-эквайера (приложение №3 Порядка взаимодействия
 * при интернет-эквайринге): на сайте обязаны быть развёрнутая оферта,
 * описание способов оплаты, информация о 3-D Secure и о контроле рисков
 * мошеннических операций.
 *
 * Раздел документа — последовательность узлов: абзац ['p' => ...] либо
 * список ['list' => [...]]. Перечисления в оферте стоят внутри пунктов,
 * а не одним списком в конце раздела, и отдельным полем их не выразить.
 */
class LegalController extends Controller
{
    private const DOCS = ['terms', 'payment', 'security', 'privacy', 'refunds'];

    /** Тексты документов — общие с Django */
    private const SOURCE = 'legal/documents.json';

    /**
     * Заголовок документа на языке интерфейса.
     *
     * Из словаря, а не константой: заголовок в теге <title> собирался
     * по словарю, а заголовок на самой странице был жёстко русским —
     * узбекская версия страницы меняла название прямо на глазах,
     * когда React перерисовывал её после загрузки.
     */
    private function title(string $doc): string
    {
        return __("ui.legal.{$doc}_title");
    }

    public function show(string $doc): Response
    {
        if (! in_array($doc, self::DOCS, true)) {
            throw new NotFoundHttpException;
        }

        $content = $this->document($doc);

        /*
         * Оферту и политику ищут по названию компании перед оплатой —
         * страница должна находиться, поэтому от индексации не закрываем.
         */
        app(Seo::class)
            ->title($this->title($doc))
            ->description($content['intro'])
            ->canonical(url("/{$doc}"));

        return Inertia::render('Legal', [
            'title' => $this->title($doc),
            'intro' => $content['intro'],
            'preamble' => $content['preamble'] ?? [],
            'blocks' => $content['blocks'],
            'updatedAt' => self::source()['updated_at'],
            'draft' => false,
            'siblings' => collect(self::DOCS)->map(fn (string $d) => [
                'href' => "/{$d}",
                'label' => $this->title($d),
                'current' => $d === $doc,
            ])->all(),
        ]);
    }

    /*
     * Контакты и реквизиты в текстах — из настроек админки, как
     * и на остальных страницах: смена почты поддержки не должна
     * требовать деплоя. Фолбэки повторяют значения сидера — на случай
     * базы, где настройка удалена руками.
     */

    private function email(): string
    {
        return (string) Setting::get('support_email', 'support@savdex.uz');
    }

    /**
     * Наименование оператора для текста оферты.
     *
     * Полное — как в учредительных документах: в исходнике оферты на
     * этих местах стоит «[полное наименование юридического лица]»,
     * и краткая форма разошлась бы с разделом реквизитов той же
     * страницы. Короткое наименование остаётся запасным на случай
     * незаполненной настройки.
     */
    private function legalName(): string
    {
        $full = trim((string) Setting::get('legal_full_name', ''));

        return $full !== '' ? $full : (string) Setting::get('legal_name', 'ООО «ANJIR-GROUP»');
    }

    /** Строка «Подпись: значение» или null, если настройка не заполнена. */
    private function requisite(string $label, string $key): ?string
    {
        $value = trim((string) Setting::get($key, ''));

        return $value === '' ? null : "{$label}: {$value}";
    }

    /**
     * Документ с подставленными наименованием, почтой и реквизитами.
     *
     * Тексты — в resources/legal/documents.json: их же читает Django
     * (python/savdex/web/legal.py), и у документа один источник.
     * Правки текста — только по новой редакции от заказчика: это
     * условия договора, а не копия страницы, и вольный пересказ
     * здесь меняет обязательства сторон.
     *
     * В строках {legal_name} и {email} — наименование оператора и почта
     * поддержки; узел списка {requisite, setting} — строка реквизита,
     * которая пропадает, если настройка не заполнена.
     *
     * @return array<string, mixed>
     */
    private function document(string $doc): array
    {
        return $this->resolve(self::source()['documents'][$doc]);
    }

    /** @return array<string, mixed> */
    private static function source(): array
    {
        return json_decode((string) file_get_contents(resource_path(self::SOURCE)), true, flags: JSON_THROW_ON_ERROR);
    }

    private function resolve(mixed $node): mixed
    {
        if (is_string($node)) {
            return strtr($node, ['{legal_name}' => $this->legalName(), '{email}' => $this->email()]);
        }

        if (! is_array($node)) {
            return $node;
        }

        if (isset($node['requisite'])) {
            return $this->requisite($node['requisite'], $node['setting']);
        }

        $resolved = array_map(fn (mixed $child) => $this->resolve($child), $node);
        $requisites = array_filter($node, fn (mixed $child) => is_array($child) && isset($child['requisite']));

        // Список реквизитов: незаполненные строки из него выпадают
        return $requisites !== [] ? array_values(array_filter($resolved)) : $resolved;
    }
}
