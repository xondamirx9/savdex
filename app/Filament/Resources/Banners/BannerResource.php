<?php

declare(strict_types=1);

namespace App\Filament\Resources\Banners;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Banners\Pages\CreateBanner;
use App\Filament\Resources\Banners\Pages\EditBanner;
use App\Filament\Resources\Banners\Pages\ListBanners;
use App\Filament\Resources\Banners\Schemas\BannerForm;
use App\Filament\Resources\Banners\Tables\BannersTable;
use App\Models\Banner;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use UnitEnum;

/**
 * Баннеры площадки.
 *
 * Акцию заводят целиком отсюда: картинка, срок, место, ссылка. Раньше
 * полоса «Скидка до 1 октября» означала задачу разработчику и деплой,
 * то есть акцию нельзя было запустить быстрее, чем за день.
 */
class BannerResource extends Resource
{
    use AuthorizesBySection;

    /** По ТЗ баннеры — тот же content, что страницы и новости (§4). */
    protected static string $accessSection = 'content';

    protected static ?string $model = Banner::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedMegaphone;

    protected static ?string $navigationLabel = 'Баннеры';

    protected static ?string $modelLabel = 'баннер';

    protected static ?string $pluralModelLabel = 'баннеры';

    protected static string|UnitEnum|null $navigationGroup = 'Контент';

    protected static ?int $navigationSort = 5;

    /**
     * Счётчик показывает висящие сейчас, а не все заведённые.
     *
     * Общее число включало бы прошлогодние акции и ничего не говорило:
     * важно, сколько баннеров видит посетитель прямо сейчас.
     */
    public static function getNavigationBadge(): ?string
    {
        $live = Banner::query()->live()->count();

        return $live > 0 ? (string) $live : null;
    }

    public static function form(Schema $schema): Schema
    {
        return BannerForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return BannersTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListBanners::route('/'),
            'create' => CreateBanner::route('/create'),
            'edit' => EditBanner::route('/{record}/edit'),
        ];
    }
}
