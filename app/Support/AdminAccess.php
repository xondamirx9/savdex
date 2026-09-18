<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\User;
use Illuminate\Support\Facades\Auth;

/**
 * Права в админ-панели: кто какой раздел видит и что в нём может.
 *
 * Единственное место, где живёт матрица «раздел × роль» из docs/admin-roles.md.
 * Раньше проверок было тридцать две, разложенных по девятнадцати файлам, и
 * каждая отвечала на один и тот же вопрос «суперадмин или нет». С девятью
 * ролями такой способ перестаёт работать: чтобы узнать, что видит продавец,
 * пришлось бы прочитать девятнадцать файлов и ничего не пропустить.
 *
 * Здесь матрица одна, и она же проверяется тестами. Ресурсы панели только
 * спрашивают: «можно ли companies.delete», — и не знают ничего про роли.
 *
 * Не всякая пара «раздел + действие» осмысленна: «настройки.модерация» ни
 * одной роли не выдаётся и никогда не вернёт истину. Гейты заводятся на все
 * пары ради одного свойства — не бывает права, которое забыли объявить, и
 * потому молча вернуло «нет» даже суперадмину.
 */
final class AdminAccess
{
    // ── Роли ────────────────────────────────────────────────────────

    public const SUPERADMIN = 'superadmin';

    public const ADMIN = 'admin';

    public const SALES = 'sales';

    public const SUPPLIER_MANAGER = 'supplier_manager';

    public const BUYER_MANAGER = 'buyer_manager';

    public const MODERATOR = 'moderator';

    public const FINANCE = 'finance';

    public const SUPPORT = 'support';

    public const CONTENT_MANAGER = 'content_manager';

    /** @var array<string, string> */
    public const ROLES = [
        self::SUPERADMIN => 'Суперадмин',
        self::ADMIN => 'Администратор',
        self::SALES => 'Отдел продаж',
        self::SUPPLIER_MANAGER => 'Менеджер поставщиков',
        self::BUYER_MANAGER => 'Менеджер покупателей',
        self::MODERATOR => 'Модератор',
        self::FINANCE => 'Финансы',
        self::SUPPORT => 'Поддержка',
        self::CONTENT_MANAGER => 'Контент-менеджер',
    ];

    // ── Действия ────────────────────────────────────────────────────

    public const VIEW = 'view';

    public const CREATE = 'create';

    public const EDIT = 'edit';

    public const DELETE = 'delete';

    public const MODERATE = 'moderate';

    public const EXPORT = 'export';

    public const IMPORT = 'import';

    /** @var array<string, string> */
    public const ACTIONS = [
        self::VIEW => 'Смотреть',
        self::CREATE => 'Создавать',
        self::EDIT => 'Изменять',
        self::DELETE => 'Удалять',
        self::MODERATE => 'Модерировать',
        self::EXPORT => 'Выгружать',
        self::IMPORT => 'Загружать',
    ];

    // ── Разделы ─────────────────────────────────────────────────────

    /** @var array<string, string> */
    public const SECTIONS = [
        'users' => 'Пользователи',
        'roles' => 'Роли и права',
        'audit' => 'Журнал действий',
        'dashboard' => 'Показатели площадки',
        'companies' => 'Компании',
        'listings' => 'Объявления и товары',
        'tenders' => 'Тендеры и потребности',
        'ittasks' => 'IT-задачи',
        'documents' => 'Документы на проверку',
        'resumes' => 'Резюме соискателей',
        'reviews' => 'Отзывы',
        'complaints' => 'Жалобы на контакты',
        'leads' => 'Лиды',
        'deals' => 'Сделки',
        'contacts' => 'Контакты',
        'tasks' => 'Задачи',
        'communications' => 'Коммуникации',
        'support' => 'Обращения в поддержку',
        'payments' => 'Счета и оплаты',
        'subscriptions' => 'Подписки',
        'refunds' => 'Возвраты и финансовые операции',
        'plans' => 'Тарифы',
        'promocodes' => 'Промокоды',
        'creditpacks' => 'Пакеты контактов',
        'finreports' => 'Финансовые отчёты',
        'content' => 'Страницы, новости, баннеры',
        'catalogs' => 'Справочники',
        'broadcasts' => 'Рассылки',
        'settings' => 'Настройки площадки',
    ];

    /**
     * Уровни доступа из матрицы ТЗ. Каждый следующий включает предыдущий.
     *
     * Выгрузка и загрузка в уровни не входят: унести список файлом и
     * посмотреть его на экране — разные по последствиям действия, и
     * выдаются они отдельно, ниже в EXTRAS.
     *
     * @var array<string, list<string>>
     */
    private const LEVELS = [
        'r' => [self::VIEW],
        'w' => [self::VIEW, self::CREATE, self::EDIT],
        'm' => [self::VIEW, self::CREATE, self::EDIT, self::MODERATE],
        'f' => [self::VIEW, self::CREATE, self::EDIT, self::MODERATE, self::DELETE],
    ];

    /**
     * Матрица. Раздела нет в списке роли — раздела нет и в панели.
     *
     * Суффикс «o» у уровня означает «только свои записи»: продавец видит
     * лидов, где ответственным указан он. Суперадмина в матрице нет: ему
     * разрешено всё, включая разделы, которых ещё не существует.
     *
     * @var array<string, array<string, string>>
     */
    private const MATRIX = [
        self::ADMIN => [
            'users' => 'w', 'audit' => 'r', 'dashboard' => 'r',
            'companies' => 'w', 'listings' => 'w', 'tenders' => 'w', 'ittasks' => 'w',
            'documents' => 'r', 'resumes' => 'm', 'reviews' => 'w', 'complaints' => 'w',
            'leads' => 'w', 'deals' => 'w', 'contacts' => 'w', 'tasks' => 'w', 'communications' => 'w',
            'support' => 'w',
            'content' => 'w', 'catalogs' => 'w', 'broadcasts' => 'r',
        ],
        self::SALES => [
            'companies' => 'r', 'listings' => 'r', 'tenders' => 'r',
            'leads' => 'wo', 'deals' => 'wo', 'contacts' => 'w',
            'tasks' => 'wo', 'communications' => 'wo',
            'promocodes' => 'w',
        ],
        self::SUPPLIER_MANAGER => [
            'companies' => 'w', 'listings' => 'r', 'tenders' => 'r',
            'documents' => 'r',
            'leads' => 'w', 'deals' => 'w', 'contacts' => 'w',
            'tasks' => 'wo', 'communications' => 'wo',
        ],
        self::BUYER_MANAGER => [
            'companies' => 'w', 'listings' => 'r', 'tenders' => 'w',
            'documents' => 'r',
            'leads' => 'w', 'deals' => 'w', 'contacts' => 'w',
            'tasks' => 'wo', 'communications' => 'wo',
        ],
        self::MODERATOR => [
            'companies' => 'm', 'listings' => 'm', 'tenders' => 'm', 'ittasks' => 'm',
            'documents' => 'm', 'resumes' => 'm', 'reviews' => 'm', 'complaints' => 'm',
            'catalogs' => 'r',
        ],
        self::FINANCE => [
            'audit' => 'r', 'companies' => 'r',
            'payments' => 'w', 'subscriptions' => 'w', 'refunds' => 'w',
            'plans' => 'r', 'promocodes' => 'w', 'creditpacks' => 'w', 'finreports' => 'r',
        ],
        self::SUPPORT => [
            'users' => 'r', 'companies' => 'r', 'listings' => 'r', 'ittasks' => 'r',
            'resumes' => 'r', 'reviews' => 'r', 'complaints' => 'r',
            'contacts' => 'r', 'tasks' => 'wo', 'communications' => 'wo',
            'support' => 'w', 'subscriptions' => 'r',
        ],
        self::CONTENT_MANAGER => [
            'content' => 'w', 'catalogs' => 'w', 'broadcasts' => 'r',
        ],
    ];

    /**
     * Выгрузка и загрузка — поимённо.
     *
     * Выгрузка уносит с площадки персональные данные целым файлом,
     * загрузка создаёт записи пачкой, минуя формы и их проверки.
     * Ни то ни другое не должно доставаться вместе с правом на правку.
     *
     * @var array<string, list<string>>
     */
    private const EXTRAS = [
        self::ADMIN => [
            'companies.export', 'companies.import',
            'listings.export', 'listings.import', 'users.export',
            'tenders.export', 'tenders.import',
        ],
        self::FINANCE => [
            'payments.export', 'subscriptions.export', 'finreports.export',
        ],
    ];

    // ── Вопросы, которые задаёт панель ──────────────────────────────

    /** Есть ли у текущего пользователя это право. */
    public static function allows(string $ability): bool
    {
        $user = Auth::user();

        return $user instanceof User && $user->hasAdminAbility($ability);
    }

    /** Все мыслимые права: по ним заводятся гейты. */
    public static function all(): array
    {
        $abilities = [];

        foreach (array_keys(self::SECTIONS) as $section) {
            foreach (array_keys(self::ACTIONS) as $action) {
                $abilities[] = $section.'.'.$action;
            }
        }

        return $abilities;
    }

    /**
     * Права роли. Неизвестная роль не получает ничего.
     *
     * Пустой набор вместо набора по умолчанию — намеренно: человек с
     * незаполненной ролью увидит пустую панель и придёт спросить, а не
     * получит молча чужие права.
     *
     * @return list<string>
     */
    public static function abilitiesFor(?string $role): array
    {
        if ($role === self::SUPERADMIN) {
            return self::all();
        }

        $abilities = [];

        foreach (self::MATRIX[$role] ?? [] as $section => $level) {
            foreach (self::LEVELS[rtrim($level, 'o')] ?? [] as $action) {
                $abilities[] = $section.'.'.$action;
            }
        }

        return array_values(array_unique([...$abilities, ...self::EXTRAS[$role] ?? []]));
    }

    /**
     * Видит ли роль в этом разделе только свои записи.
     *
     * Суперадмин и любой, кому раздел не выдан, — не «свои»: первому
     * видно всё, второму не видно ничего, и сужать там нечего.
     */
    public static function scopeIsOwn(?string $role, string $section): bool
    {
        return str_ends_with(self::MATRIX[$role][$section] ?? '', 'o');
    }

    /** Существует ли такая роль. */
    public static function isRole(?string $role): bool
    {
        return $role !== null && array_key_exists($role, self::ROLES);
    }

    /** Существует ли такое право: защита от опечатки в названии. */
    public static function isAbility(string $ability): bool
    {
        [$section, $action] = array_pad(explode('.', $ability, 2), 2, '');

        return array_key_exists($section, self::SECTIONS)
            && array_key_exists($action, self::ACTIONS);
    }

    /** «Компании · Изменять» — для экрана выдачи прав и для журнала. */
    public static function label(string $ability): string
    {
        [$section, $action] = array_pad(explode('.', $ability, 2), 2, '');

        return (self::SECTIONS[$section] ?? $section).' · '.(self::ACTIONS[$action] ?? $action);
    }

    /**
     * Права, которые имеет смысл выдавать поштучно.
     *
     * Это объединение наборов всех восьми ролей: пара «раздел + действие»,
     * которой не пользуется ни одна роль, в списке выдачи будет мусором.
     * Полный перебор нужен гейтам, а человеку — осмысленный список.
     *
     * @return array<string, string>
     */
    public static function grantable(): array
    {
        $abilities = [];

        foreach (array_keys(self::MATRIX) as $role) {
            foreach (self::abilitiesFor($role) as $ability) {
                $abilities[$ability] = self::label($ability);
            }
        }

        uksort($abilities, fn (string $a, string $b): int => array_search(explode('.', $a)[0], array_keys(self::SECTIONS), true)
            <=> array_search(explode('.', $b)[0], array_keys(self::SECTIONS), true)
            ?: strcmp($a, $b));

        return $abilities;
    }

    /**
     * Права, сгруппированные по разделам, — для списка галочек.
     *
     * @return array<string, array<string, string>>
     */
    public static function grouped(): array
    {
        $groups = [];

        foreach (self::SECTIONS as $section => $sectionLabel) {
            foreach (self::ACTIONS as $action => $actionLabel) {
                $groups[$sectionLabel][$section.'.'.$action] = $actionLabel;
            }
        }

        return $groups;
    }
}
