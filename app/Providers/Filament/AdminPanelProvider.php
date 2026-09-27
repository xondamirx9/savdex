<?php

declare(strict_types=1);

namespace App\Providers\Filament;

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
use App\Support\AdminAccess;
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
            ->login()
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
                NavigationItem::make('Баннеры')
                    ->url('/admin/python?next=/py/admin/site/banner/')
                    ->icon('heroicon-o-megaphone')
                    ->group('Контент')
                    ->sort(5)
                    // Значок считает висящие сейчас, а не все заведённые
                    ->badge(fn (): ?string => ($live = Banner::query()->live()->count()) > 0 ? (string) $live : null)
                    ->visible(fn (): bool => AdminAccess::allows('content.view')),
                NavigationItem::make('Настройки')
                    ->url('/admin/python?next=/py/admin/site/setting/')
                    ->icon('heroicon-o-adjustments-horizontal')
                    ->group('Система')
                    ->sort(3)
                    ->visible(fn (): bool => AdminAccess::allows('settings.view')),
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
