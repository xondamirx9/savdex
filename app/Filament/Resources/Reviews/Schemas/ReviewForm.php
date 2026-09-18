<?php

declare(strict_types=1);

namespace App\Filament\Resources\Reviews\Schemas;

use App\Models\Company;
use App\Models\Listing;
use App\Models\Review;
use Closure;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Components\Utilities\Get;
use Filament\Schemas\Schema;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;

/**
 * Форма отзыва.
 *
 * Правка нужна безусловно: опечатка по просьбе автора, персональные
 * данные в тексте, клевета. Заведение вручную — для переноса отзывов,
 * собранных вне сайта.
 *
 * Происхождение в форме не редактируется: его проставляет код при
 * сохранении. Поле, которым можно выдать заведённый отзыв за
 * покупательский, обесценило бы саму пометку.
 */
class ReviewForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Кто о ком')
                ->description('Один отзыв на пару «автор — компания — объявление». Повтор той же пары не заводится: правьте существующий.')
                ->schema([
                    Select::make('company_id')
                        ->label('О какой компании')
                        ->relationship('company', 'name')
                        ->getOptionLabelFromRecordUsing(fn (Company $record): string => $record->name)
                        ->required()
                        ->searchable()
                        ->preload(),

                    Select::make('author_company_id')
                        ->label('От какой компании')
                        ->relationship('authorCompany', 'name')
                        ->getOptionLabelFromRecordUsing(fn (Company $record): string => $record->name)
                        ->required()
                        ->searchable()
                        ->preload()
                        ->different('company_id')
                        /*
                         * Повтор пары ловится здесь, а не базой.
                         *
                         * Индекс на (компания, автор, объявление) от
                         * повтора не спасает: у отзыва о компании вообще
                         * объявления нет, а NULL в индексе не равен NULL —
                         * и второй отзыв той же пары заводился молча,
                         * дважды попадая в рейтинг. Когда объявление
                         * указано, индекс срабатывал, но ошибкой базы:
                         * админ видел пятисотую страницу и терял текст.
                         */
                        ->rule(fn (Get $get, ?Model $record): Closure => function (string $attribute, mixed $value, Closure $fail) use ($get, $record): void {
                            $listing = $get('listing_id');

                            $exists = Review::query()
                                ->where('company_id', $get('company_id'))
                                ->where('author_company_id', $value)
                                ->where(fn (Builder $q) => $listing
                                    ? $q->where('listing_id', $listing)
                                    : $q->whereNull('listing_id'))
                                ->when($record !== null, fn (Builder $q) => $q->whereKeyNot($record->getKey()))
                                ->exists();

                            if ($exists) {
                                $fail('Отзыв этой компании об этой уже есть — откройте и поправьте его.');
                            }
                        })
                        ->helperText('Компания не может отозваться о себе'),

                    Select::make('listing_id')
                        ->label('По какому объявлению')
                        ->relationship('listing', 'title')
                        ->getOptionLabelFromRecordUsing(fn (Listing $record): string => $record->title)
                        ->searchable()
                        ->preload()
                        ->helperText('Необязательно: отзыв может быть о работе с компанией вообще'),
                ])
                ->columns(2),

            Section::make('Оценка')
                ->schema([
                    Select::make('rating')
                        ->label('Общая оценка')
                        ->options([5 => '5 — отлично', 4 => '4 — хорошо', 3 => '3 — нормально', 2 => '2 — плохо', 1 => '1 — очень плохо'])
                        ->required(),

                    Select::make('rating_description')
                        ->label('Соответствие описанию')
                        ->options(array_combine(range(1, 5), range(1, 5))),

                    Select::make('rating_response')
                        ->label('Скорость ответа')
                        ->options(array_combine(range(1, 5), range(1, 5))),

                    Select::make('rating_deadlines')
                        ->label('Соблюдение сроков')
                        ->options(array_combine(range(1, 5), range(1, 5))),

                    Select::make('rating_quality')
                        ->label('Качество товара')
                        ->options(array_combine(range(1, 5), range(1, 5))),

                    Toggle::make('deal_confirmed')
                        ->label('Сделка подтверждена')
                        ->helperText('Отмечается, когда за отзывом стоит оплаченное раскрытие контакта'),
                ])
                ->columns(3),

            Section::make('Текст')
                ->schema([
                    Textarea::make('body')
                        ->label('Отзыв')
                        ->required()
                        ->minLength(10)
                        ->maxLength(5000)
                        ->rows(5),

                    Textarea::make('reply')
                        ->label('Ответ компании')
                        ->maxLength(5000)
                        ->rows(3)
                        ->helperText('Необязательно. Обычно пишет сама компания из кабинета'),

                    Select::make('status')
                        ->label('Статус')
                        ->options([
                            Review::STATUS_PUBLISHED => 'Опубликован',
                            Review::STATUS_MODERATION => 'На проверке',
                            Review::STATUS_HIDDEN => 'Скрыт',
                        ])
                        ->default(Review::STATUS_PUBLISHED)
                        ->required()
                        ->helperText('Опубликованный сразу попадает на витрину и в рейтинг компании'),
                ])
                ->columns(1),
        ]);
    }
}
