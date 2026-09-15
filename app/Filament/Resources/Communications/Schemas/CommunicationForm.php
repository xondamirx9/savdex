<?php

declare(strict_types=1);

namespace App\Filament\Resources\Communications\Schemas;

use App\Models\Crm\Communication;
use App\Models\Crm\Contact;
use App\Models\Crm\Deal;
use App\Models\Crm\Lead;
use Filament\Forms\Components\DateTimePicker;
use Filament\Forms\Components\MorphToSelect;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

class CommunicationForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Разговор')
                ->schema([
                    Select::make('type')
                        ->label('Что было')
                        ->options(Communication::TYPES)
                        ->default('call')
                        ->required(),

                    DateTimePicker::make('happened_at')
                        ->label('Когда')
                        ->seconds(false)
                        ->displayFormat('d.m.Y H:i')
                        ->default(now())
                        ->required(),

                    Select::make('contact_id')
                        ->label('С кем')
                        ->options(fn (): array => Contact::query()
                            ->orderBy('name')
                            ->limit(200)
                            ->get()
                            ->mapWithKeys(fn (Contact $c): array => [$c->id => $c->label()])
                            ->all())
                        ->searchable(),

                    TextInput::make('summary')
                        ->label('О чём')
                        ->required()
                        ->maxLength(200)
                        ->columnSpanFull()
                        ->placeholder('Договорились о пробной партии 20 тонн'),
                ])
                ->columns(3),

            Section::make('К чему относится')
                ->schema([
                    MorphToSelect::make('subject')
                        ->label('Связан с')
                        ->types([
                            MorphToSelect\Type::make(Lead::class)->label('Лид')->titleAttribute('title'),
                            MorphToSelect\Type::make(Deal::class)->label('Сделка')->titleAttribute('title'),
                        ])
                        ->searchable(),
                ]),

            Section::make('Подробности')
                ->schema([
                    Textarea::make('body')
                        ->label('Как прошло')
                        ->rows(6)
                        ->columnSpanFull()
                        ->helperText('Что просили, о чём договорились, что обещали и к какому сроку'),
                ]),
        ]);
    }
}
