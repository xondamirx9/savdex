<?php

declare(strict_types=1);

namespace App\Providers\Filament;

use App\Filament\Widgets\ActivationFunnel;
use App\Filament\Widgets\PlatformStats;
use App\Filament\Widgets\RegistrationsChart;
use App\Http\Middleware\RequirePasswordChange;
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
            ->navigationGroups([
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
            ->widgets([
                PlatformStats::class,
                ActivationFunnel::class,
                RegistrationsChart::class,
            ])
            ->middleware([
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
