<?php

declare(strict_types=1);

namespace App\Filament\Resources\CompanyDocuments;

use App\Filament\Resources\CompanyDocuments\Pages\ListCompanyDocuments;
use App\Filament\Resources\CompanyDocuments\Tables\CompanyDocumentsTable;
use App\Models\CompanyDocument;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use UnitEnum;

/**
 * Очередь документов на проверку.
 *
 * Файл загружает компания, модератор его открывает и решает — принять
 * или отклонить с причиной. Ни создавать, ни редактировать документы
 * из админки нельзя: подменять чужой файл значит подделывать основание
 * верификации.
 */
class CompanyDocumentResource extends Resource
{
    protected static ?string $model = CompanyDocument::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedDocumentCheck;

    protected static ?string $navigationLabel = 'Документы на проверку';

    protected static ?string $modelLabel = 'документ';

    protected static ?string $pluralModelLabel = 'документы';

    protected static string|UnitEnum|null $navigationGroup = 'Модерация';

    protected static ?int $navigationSort = 3;

    public static function getNavigationBadge(): ?string
    {
        $count = CompanyDocument::query()
            ->where('moderation_status', CompanyDocument::STATUS_PENDING)
            ->whereIn('type', array_keys(CompanyDocument::VERIFICATION_TYPES))
            ->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'warning';
    }

    public static function table(Table $table): Table
    {
        return CompanyDocumentsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListCompanyDocuments::route('/'),
        ];
    }
}
