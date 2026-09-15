<?php

declare(strict_types=1);

namespace App\Filament\Resources\Leads;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Leads\Pages\CreateLead;
use App\Filament\Resources\Leads\Pages\EditLead;
use App\Filament\Resources\Leads\Pages\ListLeads;
use App\Filament\Resources\Leads\Schemas\LeadForm;
use App\Filament\Resources\Leads\Tables\LeadsTable;
use App\Models\Crm\Lead;
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
 * Лиды — обращения, из которых может вырасти клиент.
 *
 * Продавец видит своих и нераспределённых; руководитель и менеджеры
 * направлений — всех. Решает это область видимости роли, а не сам
 * ресурс: сужать список в каждом разделе по-своему значит однажды
 * забыть сузить.
 */
class LeadResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'leads';

    protected static ?string $model = Lead::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedInboxArrowDown;

    protected static ?string $navigationLabel = 'Лиды';

    protected static ?string $modelLabel = 'лид';

    protected static ?string $pluralModelLabel = 'лиды';

    protected static string|UnitEnum|null $navigationGroup = 'CRM';

    protected static ?int $navigationSort = 1;

    /** Счётчик — необработанные: лид, до которого не дошли руки, остывает. */
    public static function getNavigationBadge(): ?string
    {
        $count = AdminScope::apply(Lead::query(), 'leads', 'owner_id', orphansVisible: true)
            ->where('status', Lead::STATUS_NEW)
            ->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'warning';
    }

    /**
     * Сужение на уровне запроса, а не после выборки.
     *
     * Чужой лид не должен попасть ни в список, ни в счётчик, ни в
     * выгрузку — скрыть строку в таблице недостаточно.
     */
    public static function getEloquentQuery(): Builder
    {
        return AdminScope::apply(parent::getEloquentQuery(), 'leads', 'owner_id', orphansVisible: true);
    }

    /** Прямая ссылка на чужую карточку должна отдавать отказ. */
    public static function canView(Model $record): bool
    {
        return parent::canView($record) && AdminScope::owns('leads', $record->owner_id);
    }

    public static function canEdit(Model $record): bool
    {
        return parent::canEdit($record) && AdminScope::owns('leads', $record->owner_id);
    }

    public static function canDelete(Model $record): bool
    {
        return parent::canDelete($record) && AdminScope::owns('leads', $record->owner_id);
    }

    public static function form(Schema $schema): Schema
    {
        return LeadForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return LeadsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListLeads::route('/'),
            'create' => CreateLead::route('/create'),
            'edit' => EditLead::route('/{record}/edit'),
        ];
    }
}
