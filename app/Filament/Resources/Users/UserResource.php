<?php

namespace App\Filament\Resources\Users;

use App\Filament\Resources\Users\Pages\CreateUser;
use App\Filament\Resources\Users\Pages\EditUser;
use App\Filament\Resources\Users\Pages\ListUsers;
use App\Filament\Resources\Users\Schemas\UserForm;
use App\Filament\Resources\Users\Tables\UsersTable;
use App\Models\User;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\SoftDeletingScope;
use Illuminate\Support\Facades\Auth;

class UserResource extends Resource
{
    protected static ?string $model = User::class;

    protected static ?string $navigationLabel = 'Пользователи';

    protected static ?string $modelLabel = 'пользователь';

    protected static ?string $pluralModelLabel = 'пользователи';

    protected static string|\UnitEnum|null $navigationGroup = 'Система';

    protected static ?int $navigationSort = 1;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedRectangleStack;

    /**
     * Управление пользователями — только суперадмин: иначе модератор
     * заведёт себе второго администратора и обойдёт любое ограничение.
     *
     * Проверка стоит на каждом действии, а не только на canViewAny.
     * canViewAny прячет раздел из меню, но страницы create/edit
     * авторизуются через canCreate/canEdit, а те без политики модели
     * в нестрогом режиме Filament отвечают «разрешено». Модератор,
     * набрав /admin/users/create руками, заводил себе суперадмина —
     * список был скрыт, а сама страница открыта.
     */
    public static function canViewAny(): bool
    {
        return static::onlySuperadmin();
    }

    public static function canView(Model $record): bool
    {
        return static::onlySuperadmin();
    }

    public static function canCreate(): bool
    {
        return static::onlySuperadmin();
    }

    public static function canEdit(Model $record): bool
    {
        return static::onlySuperadmin();
    }

    public static function canDelete(Model $record): bool
    {
        return static::onlySuperadmin();
    }

    public static function canDeleteAny(): bool
    {
        return static::onlySuperadmin();
    }

    public static function canForceDelete(Model $record): bool
    {
        return static::onlySuperadmin();
    }

    public static function canRestore(Model $record): bool
    {
        return static::onlySuperadmin();
    }

    /** Доступ к разделу в целом — тоже суперадмину (меню, глобальный поиск). */
    public static function canAccess(): bool
    {
        return static::onlySuperadmin();
    }

    private static function onlySuperadmin(): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function form(Schema $schema): Schema
    {
        return UserForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return UsersTable::configure($table);
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
            'index' => ListUsers::route('/'),
            'create' => CreateUser::route('/create'),
            'edit' => EditUser::route('/{record}/edit'),
        ];
    }

    public static function getRecordRouteBindingEloquentQuery(): Builder
    {
        return parent::getRecordRouteBindingEloquentQuery()
            ->withoutGlobalScopes([
                SoftDeletingScope::class,
            ]);
    }
}
