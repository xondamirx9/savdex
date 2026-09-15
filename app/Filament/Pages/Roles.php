<?php

declare(strict_types=1);

namespace App\Filament\Pages;

use App\Models\User;
use App\Support\AdminAccess;
use App\Support\AdminLog;
use BackedEnum;
use Filament\Actions\Action;
use Filament\Forms\Components\CheckboxList;
use Filament\Forms\Components\Placeholder;
use Filament\Forms\Components\Select;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Concerns\InteractsWithTable;
use Filament\Tables\Contracts\HasTable;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use UnitEnum;

/**
 * Кто работает в панели и что каждому доступно.
 *
 * Отдельная страница, а не раздел «Пользователи»: там список всех
 * двадцати шести тысяч клиентов площадки, среди которых сотрудников
 * — единицы. Искать своих в чужом списке неудобно, а выдавать доступ
 * в том же окне, где правят телефон клиента, ещё и опасно.
 *
 * Всё, что здесь происходит, попадает в журнал действий: выдача и
 * отзыв прав — первое, что смотрят, когда разбираются в инциденте.
 */
class Roles extends Page implements HasTable
{
    use InteractsWithTable;

    public static function canAccess(): bool
    {
        return AdminAccess::allows('roles.view');
    }

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedKey;

    protected static ?string $navigationLabel = 'Роли и права';

    protected static string|UnitEnum|null $navigationGroup = 'Система';

    protected static ?int $navigationSort = 5;

    protected string $view = 'filament.pages.roles';

    public function getTitle(): string
    {
        return 'Роли и права';
    }

    public function getSubheading(): ?string
    {
        return 'Роль задаёт базовый набор прав. Личные права — исключения поверх роли для конкретного человека.';
    }

    /**
     * Выдача доступа — действие страницы, а не строки таблицы.
     *
     * Человека, которому доступ выдают, в таблице ещё нет: он клиент
     * площадки, а таблица показывает сотрудников.
     *
     * @return array<Action>
     */
    protected function getHeaderActions(): array
    {
        return [
            Action::make('grantAccess')
                ->label('Выдать доступ')
                ->icon('heroicon-o-user-plus')
                ->visible(fn (): bool => AdminAccess::allows('roles.create'))
                ->schema([
                    Select::make('user_id')
                        ->label('Кому')
                        ->options(fn (): array => User::query()
                            ->where('is_admin', false)
                            ->orderBy('name')
                            ->limit(50)
                            ->pluck('name', 'id')
                            ->all())
                        ->searchable()
                        ->getSearchResultsUsing(fn (string $search): array => User::query()
                            ->where('is_admin', false)
                            ->where(fn (Builder $q) => $q->where('name', 'like', "%{$search}%")
                                ->orWhere('email', 'like', "%{$search}%"))
                            ->limit(50)
                            ->pluck('name', 'id')
                            ->all())
                        ->required()
                        ->helperText('Доступ выдаётся существующему пользователю площадки — заводить вторую учётку незачем'),

                    Select::make('admin_role')
                        ->label('Роль')
                        ->options(AdminAccess::ROLES)
                        ->default(AdminAccess::MODERATOR)
                        ->required()
                        ->live()
                        ->helperText('Что откроет роль — видно ниже'),

                    Placeholder::make('preview')
                        ->label('Роль открывает')
                        ->content(fn ($get): string => self::describeRole((string) $get('admin_role'))),
                ])
                ->action(function (array $data): void {
                    $user = User::findOrFail($data['user_id']);

                    $user->forceFill([
                        'is_admin' => true,
                        'admin_role' => $data['admin_role'],
                    ])->save();

                    AdminLog::record('granted', 'roles', $user,
                        ['after' => ['admin_role' => $data['admin_role']]],
                        'Выдан доступ в панель: '.(AdminAccess::ROLES[$data['admin_role']] ?? $data['admin_role']),
                    );

                    Notification::make()->title('Доступ выдан')->success()->send();
                }),
        ];
    }

    public function table(Table $table): Table
    {
        return $table
            ->query(User::query()->where('is_admin', true))
            ->defaultSort('name')
            ->columns([
                TextColumn::make('name')
                    ->label('Сотрудник')
                    ->searchable()
                    ->description(fn (User $u): string => $u->email),

                TextColumn::make('admin_role')
                    ->label('Роль')
                    ->badge()
                    ->state(fn (User $u): string => $u->adminRoleLabel() ?? '—')
                    ->color(fn (User $u): string => $u->isSuperadmin() ? 'danger' : 'warning'),

                TextColumn::make('abilities')
                    ->label('Прав всего')
                    ->badge()
                    ->color('gray')
                    ->state(fn (User $u): string => $u->isSuperadmin()
                        ? 'все'
                        : (string) count($u->adminAbilities())),

                TextColumn::make('personal')
                    ->label('Лично')
                    // Именно исключения, а не общее число: столбец отвечает
                    // на вопрос «у кого права отличаются от роли»
                    ->state(fn (User $u): string => self::personalSummary($u))
                    ->badge()
                    ->color(fn (User $u): string => self::personalSummary($u) === '—' ? 'gray' : 'info'),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => $state === 'active' ? 'Активен' : 'Заблокирован')
                    ->color(fn (string $state): string => $state === 'active' ? 'success' : 'danger'),

                TextColumn::make('last_login_at')
                    ->label('Последний вход')
                    ->dateTime('d.m.Y H:i')
                    ->placeholder('не входил')
                    ->sortable(),
            ])
            ->filters([
                SelectFilter::make('admin_role')
                    ->label('Роль')
                    ->options(AdminAccess::ROLES),
            ])
            ->recordActions([
                Action::make('changeRole')
                    ->label('Роль')
                    ->icon('heroicon-o-identification')
                    ->visible(fn (): bool => AdminAccess::allows('roles.edit'))
                    ->fillForm(fn (User $record): array => ['admin_role' => $record->admin_role])
                    ->schema([
                        Select::make('admin_role')
                            ->label('Роль')
                            ->options(AdminAccess::ROLES)
                            ->required()
                            ->live(),

                        Placeholder::make('preview')
                            ->label('Роль открывает')
                            ->content(fn ($get): string => self::describeRole((string) $get('admin_role'))),
                    ])
                    ->action(function (User $record, array $data): void {
                        if (! self::mayChange($record, $data['admin_role'])) {
                            return;
                        }

                        $was = $record->admin_role;
                        $record->forceFill(['admin_role' => $data['admin_role']])->save();

                        AdminLog::record('granted', 'roles', $record, [
                            'before' => ['admin_role' => $was],
                            'after' => ['admin_role' => $data['admin_role']],
                        ]);

                        Notification::make()->title('Роль изменена')->success()->send();
                    }),

                Action::make('personalRights')
                    ->label('Личные права')
                    ->icon('heroicon-o-adjustments-horizontal')
                    ->visible(fn (User $record): bool => AdminAccess::allows('roles.edit') && ! $record->isSuperadmin())
                    ->modalDescription('Поверх роли. Отзыв сильнее выдачи: право в обоих списках не достанется никому.')
                    ->fillForm(fn (User $record): array => [
                        'grant' => $record->admin_permissions['grant'] ?? [],
                        'revoke' => $record->admin_permissions['revoke'] ?? [],
                    ])
                    ->schema([
                        CheckboxList::make('grant')
                            ->label('Выдать дополнительно')
                            ->options(AdminAccess::grantable())
                            ->searchable()
                            ->bulkToggleable()
                            ->columns(2),

                        CheckboxList::make('revoke')
                            ->label('Отобрать у роли')
                            ->options(AdminAccess::grantable())
                            ->searchable()
                            ->bulkToggleable()
                            ->columns(2),
                    ])
                    ->action(function (User $record, array $data): void {
                        $was = $record->admin_permissions ?? [];

                        $record->forceFill(['admin_permissions' => [
                            'grant' => array_values($data['grant'] ?? []),
                            'revoke' => array_values($data['revoke'] ?? []),
                        ]])->save();

                        AdminLog::record('granted', 'roles', $record, [
                            'before' => ['права' => self::flatten($was)],
                            'after' => ['права' => self::flatten($record->admin_permissions ?? [])],
                        ]);

                        Notification::make()->title('Личные права сохранены')->success()->send();
                    }),

                Action::make('abilities')
                    ->label('Что доступно')
                    ->icon('heroicon-o-eye')
                    ->color('gray')
                    ->modalHeading(fn (User $record): string => 'Что доступно: '.$record->name)
                    ->modalSubmitAction(false)
                    ->modalCancelActionLabel('Закрыть')
                    ->modalContent(fn (User $record) => view('filament.role-abilities', [
                        'user' => $record,
                        'rows' => self::abilityRows($record),
                    ])),

                Action::make('revokeAccess')
                    ->label(fn (User $record): string => $record->is_admin ? 'Отключить доступ' : 'Вернуть доступ')
                    ->icon('heroicon-o-no-symbol')
                    ->color('danger')
                    ->requiresConfirmation()
                    ->modalDescription('Доступ в панель снимается целиком. Роль и личные права сохраняются — если доступ вернут, они окажутся прежними.')
                    ->visible(fn (): bool => AdminAccess::allows('roles.delete'))
                    ->action(function (User $record): void {
                        if (! self::mayChange($record, null)) {
                            return;
                        }

                        $record->forceFill(['is_admin' => false])->save();

                        AdminLog::record('revoked', 'roles', $record, [
                            'before' => ['доступ в панель' => 'есть'],
                            'after' => ['доступ в панель' => 'нет'],
                        ]);

                        Notification::make()->title('Доступ отключён')->success()->send();
                    }),
            ])
            ->emptyStateHeading('Сотрудников нет')
            ->emptyStateDescription('Выдайте доступ существующему пользователю площадки кнопкой выше.');
    }

    // ── Помощники ───────────────────────────────────────────────────

    /**
     * Последнего суперадмина нельзя ни понизить, ни отключить.
     *
     * Панель без владельца чинится только руками в базе, и обнаружится
     * это в тот момент, когда понадобится что-то срочно поправить.
     */
    private static function mayChange(User $record, ?string $newRole): bool
    {
        $losesPower = $record->isSuperadmin() && $newRole !== AdminAccess::SUPERADMIN;

        if (! $losesPower) {
            return true;
        }

        $others = User::query()
            ->where('is_admin', true)
            ->where('admin_role', AdminAccess::SUPERADMIN)
            ->where('status', 'active')
            ->whereKeyNot($record->getKey())
            ->exists();

        if ($others) {
            return true;
        }

        Notification::make()
            ->title('Это последний суперадмин')
            ->body('Сначала назначьте суперадминов кого-то ещё, иначе панель останется без владельца.')
            ->danger()
            ->persistent()
            ->send();

        return false;
    }

    /** Коротко, что открывает роль: сколько разделов и какие главные. */
    private static function describeRole(string $role): string
    {
        if ($role === AdminAccess::SUPERADMIN) {
            return 'Все разделы без исключения, включая те, что появятся позже.';
        }

        $sections = [];

        foreach (AdminAccess::abilitiesFor($role) as $ability) {
            $sections[explode('.', $ability)[0]] = true;
        }

        if ($sections === []) {
            return 'Ничего — роль не найдена.';
        }

        $names = array_map(
            fn (string $s): string => AdminAccess::SECTIONS[$s] ?? $s,
            array_keys($sections),
        );

        return implode(', ', $names).'.';
    }

    /** «—», «+2», «−1», «+2 / −1» — сколько исключений поверх роли. */
    private static function personalSummary(User $user): string
    {
        $grant = count($user->admin_permissions['grant'] ?? []);
        $revoke = count($user->admin_permissions['revoke'] ?? []);

        return match (true) {
            $grant === 0 && $revoke === 0 => '—',
            $revoke === 0 => "+{$grant}",
            $grant === 0 => "−{$revoke}",
            default => "+{$grant} / −{$revoke}",
        };
    }

    /**
     * Права по разделам: что от роли, что выдано лично.
     *
     * Человек, который разбирается «почему он это видит», должен
     * получить ответ, а не список из восьмидесяти строк.
     *
     * @return array<string, array{от роли: list<string>, лично: list<string>}>
     */
    private static function abilityRows(User $user): array
    {
        $fromRole = AdminAccess::abilitiesFor($user->admin_role);
        $rows = [];

        foreach ($user->adminAbilities() as $ability) {
            [$section, $action] = explode('.', $ability, 2);
            $label = AdminAccess::ACTIONS[$action] ?? $action;
            $name = AdminAccess::SECTIONS[$section] ?? $section;

            $rows[$name][in_array($ability, $fromRole, true) ? 'от роли' : 'лично'][] = $label;
        }

        ksort($rows);

        return $rows;
    }

    /**
     * @param  array<string, mixed>  $permissions
     */
    private static function flatten(array $permissions): string
    {
        $parts = [];

        foreach (['grant' => 'выдано', 'revoke' => 'отозвано'] as $key => $word) {
            $list = $permissions[$key] ?? [];

            if ($list !== []) {
                $parts[] = $word.': '.implode(', ', $list);
            }
        }

        return $parts === [] ? 'нет' : implode('; ', $parts);
    }
}
