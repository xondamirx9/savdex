<?php

declare(strict_types=1);

namespace App\Filament\Resources\Communications;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Communications\Pages\CreateCommunication;
use App\Filament\Resources\Communications\Pages\EditCommunication;
use App\Filament\Resources\Communications\Pages\ListCommunications;
use App\Filament\Resources\Communications\Schemas\CommunicationForm;
use App\Filament\Resources\Communications\Tables\CommunicationsTable;
use App\Models\Crm\Communication;
use App\Support\AdminScope;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use UnitEnum;

/**
 * Коммуникации — история переговоров.
 *
 * Заводится руками: интеграции с почтой и телефонией пока нет. Но
 * история нужна уже сейчас — без неё она живёт в голове одного продавца
 * и уходит вместе с ним.
 */
class CommunicationResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'communications';

    protected static ?string $model = Communication::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedPhoneArrowUpRight;

    protected static ?string $navigationLabel = 'Коммуникации';

    protected static ?string $modelLabel = 'запись разговора';

    protected static ?string $pluralModelLabel = 'коммуникации';

    protected static string|UnitEnum|null $navigationGroup = 'CRM';

    protected static ?int $navigationSort = 5;

    public static function getEloquentQuery(): Builder
    {
        return AdminScope::apply(parent::getEloquentQuery(), 'communications', 'author_id');
    }

    public static function canView(Model $record): bool
    {
        return parent::canView($record) && AdminScope::owns('communications', $record->author_id);
    }

    public static function canEdit(Model $record): bool
    {
        return parent::canEdit($record) && AdminScope::owns('communications', $record->author_id);
    }

    public static function canDelete(Model $record): bool
    {
        return parent::canDelete($record) && AdminScope::owns('communications', $record->author_id);
    }

    public static function form(Schema $schema): Schema
    {
        return CommunicationForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return CommunicationsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListCommunications::route('/'),
            'create' => CreateCommunication::route('/create'),
            'edit' => EditCommunication::route('/{record}/edit'),
        ];
    }
}
