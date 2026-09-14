<?php

namespace App\Filament\Resources\LandingBlocks;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\LandingBlocks\Pages\CreateLandingBlock;
use App\Filament\Resources\LandingBlocks\Pages\EditLandingBlock;
use App\Filament\Resources\LandingBlocks\Pages\ListLandingBlocks;
use App\Filament\Resources\LandingBlocks\Schemas\LandingBlockForm;
use App\Filament\Resources\LandingBlocks\Tables\LandingBlocksTable;
use App\Models\LandingBlock;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;

class LandingBlockResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'content';

    protected static ?string $model = LandingBlock::class;

    protected static ?string $navigationLabel = 'Главная страница';

    protected static ?string $modelLabel = 'блок';

    protected static ?string $pluralModelLabel = 'блоки главной';

    protected static string|\UnitEnum|null $navigationGroup = 'Контент';

    protected static ?int $navigationSort = 1;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedRectangleStack;

    public static function form(Schema $schema): Schema
    {
        return LandingBlockForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return LandingBlocksTable::configure($table);
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
            'index' => ListLandingBlocks::route('/'),
            'create' => CreateLandingBlock::route('/create'),
            'edit' => EditLandingBlock::route('/{record}/edit'),
        ];
    }
}
