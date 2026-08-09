<?php

declare(strict_types=1);

namespace App\Filament\Resources\Users\Schemas;

use App\Models\User;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Components\Utilities\Get;
use Filament\Schemas\Schema;
use Illuminate\Support\Str;

/**
 * Пользователь: создание доступа вручную (§6.3 ТЗ).
 *
 * Пароль генерируется, а не вводится: администратор придумает
 * запоминающийся, а значит слабый — и одинаковый для всех, кому
 * заводит доступ. Флаг «сменить при входе» ставится автоматически.
 */
class UserForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Человек')
                ->schema([
                    TextInput::make('name')
                        ->label('Имя')
                        ->required()
                        ->maxLength(120),

                    TextInput::make('email')
                        ->label('Почта')
                        ->email()
                        ->required()
                        ->unique(ignoreRecord: true)
                        ->maxLength(190),

                    TextInput::make('phone')
                        ->label('Телефон')
                        ->tel()
                        ->maxLength(20),

                    Select::make('locale')
                        ->label('Язык интерфейса')
                        ->options([
                            'ru' => 'Русский',
                            'uz' => 'Oʻzbekcha',
                            'en' => 'English',
                            'zh' => '中文',
                            'tr' => 'Türkçe',
                        ])
                        ->default('ru')
                        ->required(),
                ])
                ->columns(2),

            Section::make('Компания')
                ->schema([
                    Select::make('company_id')
                        ->label('Компания')
                        ->relationship('company', 'name')
                        ->searchable()
                        ->preload()
                        ->helperText('Пусто — человек ещё не завёл компанию'),

                    Select::make('company_role')
                        ->label('Роль в компании')
                        ->options([
                            User::ROLE_OWNER => 'Владелец',
                            User::ROLE_MANAGER => 'Сотрудник',
                        ])
                        ->default(User::ROLE_OWNER),
                ])
                ->columns(2),

            Section::make('Доступ в админку')
                ->schema([
                    Toggle::make('is_admin')
                        ->label('Доступ в панель управления')
                        ->live()
                        // Флаг отвечает за «пускать ли вообще», роль —
                        // за «что видно». Разделение позволяет отозвать
                        // доступ целиком, не разбираясь в роли
                        ->helperText('Отдельно от роли: снимает доступ целиком'),

                    Select::make('admin_role')
                        ->label('Роль в админке')
                        ->options(User::ADMIN_ROLES)
                        ->default(User::ADMIN_MODERATOR)
                        ->visible(fn (Get $get): bool => (bool) $get('is_admin'))
                        ->required(fn (Get $get): bool => (bool) $get('is_admin'))
                        ->helperText('Модератор: объявления, компании, жалобы. Суперадмин: всё, включая биллинг, настройки и выдачу доступов'),

                    Select::make('status')
                        ->label('Статус')
                        ->options([
                            'active' => 'Активен',
                            'blocked' => 'Заблокирован',
                        ])
                        ->default('active')
                        ->required(),
                ])
                ->columns(3),

            Section::make('Пароль')
                ->schema([
                    TextInput::make('password')
                        ->label('Пароль')
                        ->password()
                        ->revealable()
                        ->dehydrated(fn (?string $state): bool => filled($state))
                        // При создании генерируем сразу: администратор
                        // придумает слабый и одинаковый для всех
                        ->default(fn (): string => Str::password(12, symbols: false))
                        ->helperText('Передайте лично. Человек обязан сменить его при первом входе.')
                        ->maxLength(72),

                    Toggle::make('must_change_password')
                        ->label('Требовать смену пароля при входе')
                        ->default(true),
                ])
                ->columns(2)
                ->visibleOn('create'),
        ]);
    }
}
