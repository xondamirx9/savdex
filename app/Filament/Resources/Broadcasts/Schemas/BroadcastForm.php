<?php

declare(strict_types=1);

namespace App\Filament\Resources\Broadcasts\Schemas;

use App\Models\Broadcast;
use App\Models\Plan;
use App\Models\User;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Components\Utilities\Get;
use Filament\Schemas\Schema;

/**
 * Форма рассылки уведомлений.
 *
 * Отправка необратима: уведомление уходит тысячам людей и отозвать
 * его нельзя. Поэтому здесь показывается охват до отправки, а сама
 * отправка вынесена отдельным действием со вторым подтверждением.
 */
class BroadcastForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Сообщение')
                ->schema([
                    TextInput::make('title')
                        ->label('Заголовок')
                        ->required()
                        ->maxLength(190)
                        ->helperText('Видно в списке уведомлений и в колокольчике'),

                    Textarea::make('body')
                        ->label('Текст')
                        ->required()
                        ->rows(4)
                        ->maxLength(2000),

                    TextInput::make('url')
                        ->label('Ссылка')
                        ->maxLength(190)
                        ->helperText('Куда ведёт нажатие. Например /news/oplata-click-uzum'),

                    Select::make('tone')
                        ->label('Тон')
                        ->options([
                            'info' => 'Обычное',
                            'success' => 'Хорошая новость',
                            'warning' => 'Предупреждение',
                            'danger' => 'Важно',
                        ])
                        ->default('info')
                        ->required(),
                ])
                ->columns(2),

            Section::make('Кому')
                ->schema([
                    Select::make('audience')
                        ->label('Получатели')
                        ->options(Broadcast::AUDIENCES)
                        ->default('all')
                        ->required()
                        ->live(),

                    Select::make('audience_value')
                        ->label('Тариф')
                        ->options(fn (): array => Plan::query()->pluck('name', 'code')->all())
                        // Поле имеет смысл только для сегмента «на тарифе»
                        ->visible(fn (Get $get): bool => $get('audience') === 'plan')
                        ->required(fn (Get $get): bool => $get('audience') === 'plan'),

                    TextInput::make('recipients_preview')
                        ->label('Получат сейчас')
                        ->disabled()
                        ->dehydrated(false)
                        ->helperText('Пересчитывается при смене сегмента')
                        ->afterStateHydrated(function (TextInput $component, Get $get): void {
                            $component->state(self::countRecipients($get('audience'), $get('audience_value')));
                        })
                        ->live(),
                ])
                ->columns(3),
        ]);
    }

    /**
     * Сколько человек получит рассылку.
     *
     * Логика повторяет Notifier::audienceQuery. Дублирование намеренное:
     * там запрос на выборку с chunkById, здесь — только счёт, и сводить
     * их в один метод значит тянуть весь Notifier в форму.
     */
    public static function countRecipients(?string $audience, ?string $value): int
    {
        $query = User::query()->where('status', 'active');

        return match ($audience) {
            'plan' => $query->whereHas('company.subscription.plan', fn ($q) => $q->where('code', $value))->count(),
            'verified' => $query->whereHas('company', fn ($q) => $q->where('verification_level', '>', 0))->count(),
            'unverified' => $query->whereHas('company', fn ($q) => $q->where('verification_level', 0))->count(),
            'no_company' => $query->whereNull('company_id')->count(),
            default => $query->count(),
        };
    }
}
