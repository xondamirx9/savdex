<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tenders;

use App\Filament\Resources\Tenders\Pages\CreateTender;
use App\Filament\Resources\Tenders\Pages\EditTender;
use App\Filament\Resources\Tenders\Pages\ListTenders;
use App\Filament\Resources\Tenders\Schemas\TenderForm;
use App\Filament\Resources\Tenders\Tables\TendersTable;
use App\Models\Tender;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;

/**
 * Тендеры — раздел «Контент»: заводит и публикует менеджер.
 *
 * Доступен любому администратору, включая модератора: размещение
 * тендеров — рутина контент-менеджера, а не право суперадмина.
 */
class TenderResource extends Resource
{
    protected static ?string $model = Tender::class;

    protected static ?string $navigationLabel = 'Тендеры';

    protected static ?string $modelLabel = 'тендер';

    protected static ?string $pluralModelLabel = 'тендеры';

    protected static string|\UnitEnum|null $navigationGroup = 'Контент';

    protected static ?int $navigationSort = 3;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedMegaphone;

    public static function form(Schema $schema): Schema
    {
        return TenderForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return TendersTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListTenders::route('/'),
            'create' => CreateTender::route('/create'),
            'edit' => EditTender::route('/{record}/edit'),
        ];
    }
}
