<?php

declare(strict_types=1);

namespace App\Providers\Filament;

use App\Filament\Widgets\ActivationFunnel;
use App\Filament\Widgets\ContentDrafts;
use App\Filament\Widgets\FinanceToday;
use App\Filament\Widgets\IntakeQueue;
use App\Filament\Widgets\ModerationQueue;
use App\Filament\Widgets\MyLeads;
use App\Filament\Widgets\MyTasks;
use App\Filament\Widgets\PlatformStats;
use App\Filament\Widgets\RegistrationsChart;
use App\Filament\Widgets\SupportQueue;
use App\Http\Middleware\RequirePasswordChange;
use App\Http\Middleware\SetAdminLocale;
use Filament\Http\Middleware\Authenticate;
use Filament\Http\Middleware\AuthenticateSession;
use Filament\Http\Middleware\DisableBladeIconComponents;
use Filament\Http\Middleware\DispatchServingFilamentEvent;
use Filament\Pages\Dashboard;
use Filament\Panel;
use Filament\PanelProvider;
use Filament\Support\Colors\Color;
use Illuminate\Cookie\Middleware\AddQueuedCookiesToResponse;
use Illuminate\Cookie\Middleware\EncryptCookies;
use Illuminate\Foundation\Http\Middleware\PreventRequestForgery;
use Illuminate\Routing\Middleware\SubstituteBindings;
use Illuminate\Session\Middleware\StartSession;
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
            ->brandLogo(fn () => new HtmlString(
                '<span style="display:flex;align-items:center;gap:10px;font-weight:700">'
                .'<img src="'.asset('images/logo-mark.svg').'" alt="" style="height:2.2rem">'
                .'<span>SAVDEX · Управление</span></span>',
            ))
            ->favicon(asset('images/logo-mark.svg'))
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
            ]);
    }
}
