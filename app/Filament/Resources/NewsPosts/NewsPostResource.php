<?php

namespace App\Filament\Resources\NewsPosts;

use App\Filament\Resources\NewsPosts\Pages\CreateNewsPost;
use App\Filament\Resources\NewsPosts\Pages\EditNewsPost;
use App\Filament\Resources\NewsPosts\Pages\ListNewsPosts;
use App\Filament\Resources\NewsPosts\Schemas\NewsPostForm;
use App\Filament\Resources\NewsPosts\Tables\NewsPostsTable;
use App\Models\NewsPost;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;

class NewsPostResource extends Resource
{
    protected static ?string $model = NewsPost::class;

    protected static ?string $navigationLabel = 'Новости';

    protected static ?string $modelLabel = 'новость';

    protected static ?string $pluralModelLabel = 'новости';

    protected static string|\UnitEnum|null $navigationGroup = 'Контент';

    protected static ?int $navigationSort = 2;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedRectangleStack;

    /**
     * Новости публикуются от имени площадки: модератор проверяет
     * чужой контент, но не выпускает свой.
     */
    public static function canViewAny(): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function form(Schema $schema): Schema
    {
        return NewsPostForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return NewsPostsTable::configure($table);
    }

    public static function getRelations(): array
    {
        return [
            //
        ];
    }

    public static function getPages(): array
    {
        return [
            'index' => ListNewsPosts::route('/'),
            'create' => CreateNewsPost::route('/create'),
            'edit' => EditNewsPost::route('/{record}/edit'),
        ];
    }
}
