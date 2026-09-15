<?php

namespace App\Filament\Resources\Companies\Pages;

use App\Filament\Resources\Companies\CompanyResource;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Actions\CreateAction;
use Filament\Resources\Pages\ListRecords;
use Filament\Schemas\Components\Tabs\Tab;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\Auth;

class ListCompanies extends ListRecords
{
    protected static string $resource = CompanyResource::class;

    protected function getHeaderActions(): array
    {
        return [
            CreateAction::make(),
        ];
    }

    /**
     * Поставщики и покупатели — виды одного списка, а не отдельные разделы.
     *
     * Вторая карточка той же компании разошлась бы с первой в первый же
     * месяц, и дальше никто бы не знал, какая верная. Здесь одна запись,
     * один набор фильтров и одна выгрузка.
     *
     * Компания с ролью «оба» попадает в обе вкладки намеренно: она
     * и продаёт, и закупает, и нужна обоим менеджерам направлений.
     *
     * @return array<string, Tab>
     */
    public function getTabs(): array
    {
        return [
            'all' => Tab::make('Все')
                ->badge(fn (): int => CompanyResource::getEloquentQuery()->count()),

            'suppliers' => Tab::make('Поставщики')
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->whereIn('primary_role', ['supplier', 'both']))
                ->badge(fn (): int => CompanyResource::getEloquentQuery()
                    ->whereIn('primary_role', ['supplier', 'both'])
                    ->count()),

            'buyers' => Tab::make('Покупатели')
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->whereIn('primary_role', ['buyer', 'both']))
                ->badge(fn (): int => CompanyResource::getEloquentQuery()
                    ->whereIn('primary_role', ['buyer', 'both'])
                    ->count()),
        ];
    }

    /**
     * Менеджер направления открывает список сразу на своей вкладке.
     *
     * Его работа — одно из двух, и лишний клик каждый раз к одному и
     * тому же фильтру раздражает быстрее, чем кажется.
     */
    public function getDefaultActiveTab(): string|int|null
    {
        $user = Auth::user();

        return match ($user instanceof User ? $user->admin_role : null) {
            AdminAccess::SUPPLIER_MANAGER => 'suppliers',
            AdminAccess::BUYER_MANAGER => 'buyers',
            default => 'all',
        };
    }
}
