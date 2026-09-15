<?php

declare(strict_types=1);

namespace App\Filament\Resources\Contacts;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Contacts\Pages\CreateContact;
use App\Filament\Resources\Contacts\Pages\EditContact;
use App\Filament\Resources\Contacts\Pages\ListContacts;
use App\Filament\Resources\Contacts\Schemas\ContactForm;
use App\Filament\Resources\Contacts\Tables\ContactsTable;
use App\Models\Crm\Contact;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use UnitEnum;

/**
 * Контакты — люди, с которыми ведут работу.
 *
 * Общие для всех, кто работает с CRM: один и тот же снабженец бывает
 * и в лиде продавца, и в сделке менеджера направления. Делить контакты
 * по ответственным значит завести на него три карточки.
 */
class ContactResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'contacts';

    protected static ?string $model = Contact::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedUsers;

    protected static ?string $navigationLabel = 'Контакты';

    protected static ?string $modelLabel = 'контакт';

    protected static ?string $pluralModelLabel = 'контакты';

    protected static string|UnitEnum|null $navigationGroup = 'CRM';

    protected static ?int $navigationSort = 3;

    public static function form(Schema $schema): Schema
    {
        return ContactForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return ContactsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListContacts::route('/'),
            'create' => CreateContact::route('/create'),
            'edit' => EditContact::route('/{record}/edit'),
        ];
    }
}
