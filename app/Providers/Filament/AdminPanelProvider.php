<?php

declare(strict_types=1);

namespace App\Providers\Filament;

use App\Filament\Pages\Auth\Login;
use App\Filament\Widgets\ActivationFunnel;
use App\Filament\Widgets\AwaitingRole;
use App\Filament\Widgets\ContentDrafts;
use App\Filament\Widgets\FinanceToday;
use App\Filament\Widgets\IntakeQueue;
use App\Filament\Widgets\ModerationQueue;
use App\Filament\Widgets\MyLeads;
use App\Filament\Widgets\MyTasks;
use App\Filament\Widgets\PlatformStats;
use App\Filament\Widgets\RegistrationsChart;
use App\Filament\Widgets\SupportQueue;
use App\Http\Controllers\Admin\DownloadExportController;
use App\Http\Controllers\Admin\PythonBridgeController;
use App\Http\Middleware\RequirePasswordChange;
use App\Http\Middleware\SetAdminLocale;
use App\Models\Banner;
use App\Models\CompanyDocument;
use App\Models\Crm\Lead;
use App\Models\Crm\Task;
use App\Models\Listing;
use App\Models\PlatformReview;
use App\Models\Review;
use App\Models\Support\Ticket;
use App\Support\AdminAccess;
use App\Support\AdminScope;
use App\Support\Appearance;
use Filament\Http\Middleware\Authenticate;
use Filament\Http\Middleware\AuthenticateSession;
use Filament\Http\Middleware\DisableBladeIconComponents;
use Filament\Http\Middleware\DispatchServingFilamentEvent;
use Filament\Navigation\NavigationItem;
use Filament\Pages\Dashboard;
use Filament\Panel;
use Filament\PanelProvider;
use Filament\Support\Colors\Color;
use Illuminate\Cookie\Middleware\AddQueuedCookiesToResponse;
use Illuminate\Cookie\Middleware\EncryptCookies;
use Illuminate\Foundation\Http\Middleware\PreventRequestForgery;
use Illuminate\Routing\Middleware\SubstituteBindings;
use Illuminate\Session\Middleware\StartSession;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\HtmlString;
use Illuminate\View\Middleware\ShareErrorsFromSession;

/**
 * Админ-панель площадки.
 *
 * Доступ проверяется в User::canAccessPanel(): одного флага is_admin
 * мало — заблокированный администратор тоже не должен входить.
 */
class AdminPanelProvider extends PanelProvider
{
    public function panel(Panel $panel): Panel
    {
        return $panel
            ->default()
            ->id('admin')
            ->path('admin')
            ->viteTheme('resources/css/filament/admin/theme.css')
            // Своя форма: почта без учёта регистра, как при входе на сайт
            ->login(Login::class)
            // Тот же синий, что на витрине: админка — часть продукта,
            // а не отдельный инструмент со своим оформлением
            ->colors([
                'primary' => Color::Blue,
            ])
            ->brandName('SAVDEX · Управление')
            /*
             * Знак берём из настроек, а не из репозитория: логотип
             * меняют в разделе «Оформление», и админка обязана
             * показывать тот же знак, что витрина. Замыкание — чтобы
             * настройка читалась при отрисовке панели, а не при
             * регистрации провайдера на каждом запросе сайта.
             */
            ->brandLogo(fn () => new HtmlString(
                '<span style="display:flex;align-items:center;gap:10px;font-weight:700">'
                .'<img src="'.e(Appearance::logo()).'" alt="" style="height:2.2rem">'
                .'<span>SAVDEX · Управление</span></span>',
            ))
            ->favicon(fn (): string => Appearance::logo())
            ->navigationGroups([
                // CRM первой: у продаж и менеджеров направлений это
                // единственная группа, с которой они работают каждый день
                'CRM',
                'Поддержка',
                'Контент',
                'Модерация',
                'Монетизация',
                'Данные',
                'Справочники',
                'Система',
            ])
            ->discoverResources(in: app_path('Filament/Resources'), for: 'App\Filament\Resources')
            ->discoverPages(in: app_path('Filament/Pages'), for: 'App\Filament\Pages')
            ->pages([
                Dashboard::class,
            ])
            ->discoverWidgets(in: app_path('Filament/Widgets'), for: 'App\Filament\Widgets')
            /*
             * Стартовый экран собирается из виджетов роли.
             *
             * Каждый виджет сам решает, показываться ли, — по праву,
             * а не по списку здесь. Поэтому продавец видит свои лиды и
             * задачи, модератор очередь на проверку, поддержка открытые
             * обращения, а показатели площадки — только тот, кому они
             * положены. Порядок задают свойства sort у самих виджетов:
             * рабочие очереди отрицательными, общая аналитика после них.
             */
            ->widgets([
                // Первым: если он показан, остальных всё равно нет
                AwaitingRole::class,
                MyLeads::class,
                MyTasks::class,
                IntakeQueue::class,
                ModerationQueue::class,
                SupportQueue::class,
                FinanceToday::class,
                ContentDrafts::class,
                PlatformStats::class,
                ActivationFunnel::class,
                RegistrationsChart::class,
            ])
            // Разделы, перенесённые на Django (этап 2 переноса): пункт меню
            // ведёт через пропуск (/admin/python) в раздел на Python.
            // Видимость — по тем же правам AdminAccess, что и у раздела
            ->navigationItems([
                // CRM на Django (этап 6): раздел Filament убран, порядок в
                // группе — прежний (Лиды 1, Сделки 2, Контакты 3, …)
                NavigationItem::make('Лиды')
                    ->url('/admin/python?next=/py/admin/crm/lead/')
                    ->icon('heroicon-o-inbox-arrow-down')
                    ->group('CRM')
                    ->sort(1)
                    // Счётчик — необработанные: лид, до которого не дошли
                    // руки, остывает. Свои и нераспределённые, как в списке
                    ->badge(fn (): ?string => ($new = AdminScope::apply(Lead::query(), 'leads', 'owner_id', orphansVisible: true)
                        ->where('status', Lead::STATUS_NEW)->count()) > 0 ? (string) $new : null, color: 'warning')
                    ->visible(fn (): bool => AdminAccess::allows('leads.view')),
                NavigationItem::make('Сделки')
                    ->url('/admin/python?next=/py/admin/crm/deal/')
                    ->icon('heroicon-o-briefcase')
                    ->group('CRM')
                    ->sort(2)
                    ->visible(fn (): bool => AdminAccess::allows('deals.view')),
                NavigationItem::make('Контакты')
                    ->url('/admin/python?next=/py/admin/crm/contact/')
                    ->icon('heroicon-o-users')
                    ->group('CRM')
                    ->sort(3)
                    ->visible(fn (): bool => AdminAccess::allows('contacts.view')),
                NavigationItem::make('Задачи')
                    ->url('/admin/python?next=/py/admin/crm/task/')
                    ->icon('heroicon-o-check-circle')
                    ->group('CRM')
                    ->sort(4)
                    // Счётчик — просроченные: срок, который уже прошёл, сам
                    // о себе не напомнит. По исполнителю, как в списке
                    ->badge(fn (): ?string => ($overdue = AdminScope::apply(Task::query(), 'tasks', 'assignee_id')
                        ->open()->whereNotNull('due_at')->where('due_at', '<', now())->count()) > 0 ? (string) $overdue : null, color: 'danger')
                    ->visible(fn (): bool => AdminAccess::allows('tasks.view')),
                NavigationItem::make('Коммуникации')
                    ->url('/admin/python?next=/py/admin/crm/communication/')
                    ->icon('heroicon-o-phone-arrow-up-right')
                    ->group('CRM')
                    ->sort(5)
                    ->visible(fn (): bool => AdminAccess::allows('communications.view')),
                NavigationItem::make('Отзывы')
                    ->url('/admin/python?next=/py/admin/moderation/review/')
                    ->icon('heroicon-o-chat-bubble-left-right')
                    ->group('Модерация')
                    ->sort(1)
                    // Счётчик — всё, что ждёт решения: премодерация и споры
                    ->badge(fn (): ?string => ($waiting = Review::query()
                        ->where(fn ($q) => $q->where('status', Review::STATUS_MODERATION)->orWhere('dispute_status', 'pending'))
                        ->count()) > 0 ? (string) $waiting : null, color: 'warning')
                    ->visible(fn (): bool => AdminAccess::allows('reviews.view')),
                NavigationItem::make('Отзывы о площадке')
                    ->url('/admin/python?next=/py/admin/moderation/platformreview/')
                    ->icon('heroicon-o-star')
                    ->group('Модерация')
                    // После «Жалоб» (2): при равном порядке пункт меню идёт
                    // раньше раздела, а «Документы» и «Резюме» — 3
                    ->sort(3)
                    ->badge(fn (): ?string => ($waiting = PlatformReview::query()
                        ->where('status', PlatformReview::STATUS_MODERATION)->count()) > 0 ? (string) $waiting : null, color: 'warning')
                    ->visible(fn (): bool => AdminAccess::allows('reviews.view')),
                // «Компании» и «Объявления» на Django (этап 6): разделы
                // Filament убраны, порядок в группе — прежний (Компании 1,
                // Объявления 2, IT-задачи 3)
                NavigationItem::make('Компании')
                    ->url('/admin/python?next=/py/admin/data/companyrecord/')
                    ->icon('heroicon-o-building-office')
                    ->group('Данные')
                    ->sort(1)
                    ->visible(fn (): bool => AdminAccess::allows('companies.view')),
                NavigationItem::make('Объявления')
                    ->url('/admin/python?next=/py/admin/data/listing/')
                    ->icon('heroicon-o-rectangle-stack')
                    ->group('Данные')
                    ->sort(2)
                    // Счётчик — очередь модерации: сюда заходят именно за ней
                    ->badge(fn (): ?string => ($waiting = Listing::query()
                        ->where('status', Listing::STATUS_MODERATION)->count()) > 0 ? (string) $waiting : null, color: 'warning')
                    ->visible(fn (): bool => AdminAccess::allows('listings.view')),
                NavigationItem::make('IT-задачи')
                    ->url('/admin/python?next=/py/admin/data/ittask/')
                    ->icon('heroicon-o-code-bracket')
                    ->group('Данные')
                    ->sort(3)
                    ->visible(fn (): bool => AdminAccess::allows('ittasks.view')),
                NavigationItem::make('Документы на проверку')
                    ->url('/admin/python?next=/py/admin/moderation/companydocument/')
                    ->icon('heroicon-o-document-check')
                    ->group('Модерация')
                    ->sort(3)
                    ->badge(fn (): ?string => ($pending = CompanyDocument::query()
                        ->where('moderation_status', CompanyDocument::STATUS_PENDING)
                        ->whereIn('type', CompanyDocument::VERIFICATION_TYPES)
                        ->count()) > 0 ? (string) $pending : null, color: 'warning')
                    ->visible(fn (): bool => AdminAccess::allows('documents.view')),
                NavigationItem::make('Резюме')
                    ->url('/admin/python?next=/py/admin/moderation/resume/')
                    ->icon('heroicon-o-identification')
                    ->group('Модерация')
                    ->sort(3)
                    ->visible(fn (): bool => AdminAccess::allows('resumes.view')),
                NavigationItem::make('Обращения')
                    ->url('/admin/python?next=/py/admin/support/ticket/')
                    ->icon('heroicon-o-lifebuoy')
                    ->group('Поддержка')
                    ->sort(1)
                    // Счётчик — открытые: обращение без ответа это долг перед клиентом
                    ->badge(fn (): ?string => ($open = Ticket::query()->open()->count()) > 0 ? (string) $open : null, color: 'warning')
                    ->visible(fn (): bool => AdminAccess::allows('support.view')),
                NavigationItem::make('Главная страница')
                    ->url('/admin/python?next=/py/admin/site/landingblock/')
                    ->icon('heroicon-o-home')
                    ->group('Контент')
                    ->sort(1)
                    ->visible(fn (): bool => AdminAccess::allows('content.view')),
                NavigationItem::make('Новости')
                    ->url('/admin/python?next=/py/admin/site/newspost/')
                    ->icon('heroicon-o-newspaper')
                    ->group('Контент')
                    ->sort(2)
                    ->visible(fn (): bool => AdminAccess::allows('content.view')),
                NavigationItem::make('Страницы и FAQ')
                    ->url('/admin/python?next=/py/admin/site/page/')
                    ->icon('heroicon-o-document-text')
                    ->group('Контент')
                    ->sort(3)
                    ->visible(fn (): bool => AdminAccess::allows('content.view')),
                NavigationItem::make('Тендеры')
                    ->url('/admin/python?next=/py/admin/tenders/tender/')
                    ->icon('heroicon-o-megaphone')
                    ->group('Контент')
                    ->sort(3)
                    ->visible(fn (): bool => AdminAccess::allows('tenders.view')),
                NavigationItem::make('Баннеры')
                    ->url('/admin/python?next=/py/admin/site/banner/')
                    ->icon('heroicon-o-megaphone')
                    ->group('Контент')
                    ->sort(5)
                    // Значок считает висящие сейчас, а не все заведённые
                    ->badge(fn (): ?string => ($live = Banner::query()->live()->count()) > 0 ? (string) $live : null)
                    ->visible(fn (): bool => AdminAccess::allows('content.view')),
                // «Пользователи» на Django (этап 6): раздел Filament убран,
                // порядок в группе — прежний (Пользователи 1, …, Роли и права 5)
                NavigationItem::make('Пользователи')
                    ->url('/admin/python?next=/py/admin/accounts/user/')
                    ->icon('heroicon-o-users')
                    ->group('Система')
                    ->sort(1)
                    ->visible(fn (): bool => AdminAccess::allows('users.view')),
                // Те же «Пользователи» на Python (savdex/accounts) с фильтром
                // «Отключённые»: тот же поиск и те же действия
                NavigationItem::make('Отключённые аккаунты')
                    ->url('/admin/python?next=/py/admin/accounts/user/%3Fstate%3Ddisabled')
                    ->icon('heroicon-o-user-minus')
                    ->group('Система')
                    // После «Пользователей» (1) и раньше «Рассылок» (тоже 2):
                    // пункты меню с равным порядком идут, как в этом списке
                    ->sort(2)
                    ->visible(fn (): bool => AdminAccess::allows('users.view')),
                NavigationItem::make('Рассылки')
                    ->url('/admin/python?next=/py/admin/system/broadcast/')
                    ->icon('heroicon-o-megaphone')
                    ->group('Система')
                    ->sort(2)
                    ->visible(fn (): bool => AdminAccess::allows('broadcasts.view')),
                NavigationItem::make('Настройки')
                    ->url('/admin/python?next=/py/admin/site/setting/')
                    ->icon('heroicon-o-adjustments-horizontal')
                    ->group('Система')
                    ->sort(3)
                    ->visible(fn (): bool => AdminAccess::allows('settings.view')),
                NavigationItem::make('Журнал действий')
                    ->url('/admin/python?next=/py/admin/journal/adminaction/')
                    ->icon('heroicon-o-clipboard-document-list')
                    ->group('Система')
                    ->sort(4)
                    ->visible(fn (): bool => AdminAccess::allows('audit.view')),
                // Экран «Роли и права» на Django (этап 6): сотрудники панели,
                // выдача и отзыв доступа — после «Журнала действий» (4)
                NavigationItem::make('Роли и права')
                    ->url('/admin/python?next=/py/admin/accounts/staffmember/')
                    ->icon('heroicon-o-key')
                    ->group('Система')
                    ->sort(5)
                    ->visible(fn (): bool => AdminAccess::allows('roles.view')),
                NavigationItem::make('Тарифы')
                    ->url('/admin/python?next=/py/admin/billing/plan/')
                    ->icon('heroicon-o-currency-dollar')
                    ->group('Монетизация')
                    ->sort(1)
                    ->visible(fn (): bool => AdminAccess::allows('plans.view')),
                NavigationItem::make('Пакеты контактов')
                    ->url('/admin/python?next=/py/admin/billing/creditpack/')
                    ->icon('heroicon-o-ticket')
                    ->group('Монетизация')
                    // Между «Финансовыми операциями» (4) и «Промокодами» (5):
                    // при равном порядке пункты меню идут раньше разделов
                    ->sort(5)
                    ->visible(fn (): bool => AdminAccess::allows('creditpacks.view')),
                NavigationItem::make('Категории')
                    ->url('/admin/python?next=/py/admin/catalogs/category/')
                    ->icon('heroicon-o-rectangle-stack')
                    ->group('Справочники')
                    ->sort(1)
                    ->visible(fn (): bool => AdminAccess::allows('catalogs.view')),
                NavigationItem::make('Типы компаний')
                    ->url('/admin/python?next=/py/admin/catalogs/companytype/')
                    ->icon('heroicon-o-briefcase')
                    ->group('Справочники')
                    ->sort(2)
                    ->visible(fn (): bool => AdminAccess::allows('catalogs.view')),
                NavigationItem::make('Страны')
                    ->url('/admin/python?next=/py/admin/geo/country/')
                    ->icon('heroicon-o-globe-alt')
                    ->group('Справочники')
                    ->sort(3)
                    ->visible(fn (): bool => AdminAccess::allows('catalogs.view')),
                NavigationItem::make('Города')
                    ->url('/admin/python?next=/py/admin/geo/city/')
                    ->icon('heroicon-o-building-office-2')
                    ->group('Справочники')
                    ->sort(4)
                    ->visible(fn (): bool => AdminAccess::allows('catalogs.view')),
            ])
            ->middleware([
                SetAdminLocale::class,
                EncryptCookies::class,
                AddQueuedCookiesToResponse::class,
                StartSession::class,
                AuthenticateSession::class,
                ShareErrorsFromSession::class,
                PreventRequestForgery::class,
                SubstituteBindings::class,
                DisableBladeIconComponents::class,
                DispatchServingFilamentEvent::class,
            ])
            ->authMiddleware([
                Authenticate::class,
                RequirePasswordChange::class,
            ])
            // Скачивание книг выгрузки — за тем же входом в админку,
            // права проверяет сам контроллер
            ->authenticatedRoutes(function (): void {
                Route::get('exports/{run}/{file}', DownloadExportController::class)
                    ->name('exports.download');

                // Переход в разделы, которые уже работают на Django
                // (этап 2 переноса): пропуск вместо общей сессии
                Route::get('python', PythonBridgeController::class)
                    ->name('python');
            });
    }
}
