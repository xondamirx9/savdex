<?php

declare(strict_types=1);

namespace App\Filament\Resources\Resumes;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Resumes\Pages\ListResumes;
use App\Filament\Resources\Resumes\Tables\ResumesTable;
use App\Models\Resume;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use UnitEnum;

/**
 * Резюме соискателей — работа модератора.
 *
 * Формы правки нет намеренно: модератор не переписывает чужую
 * биографию. Он решает, остаётся резюме в разделе или снимается,
 * и причину снятия видит сам соискатель у себя в кабинете.
 *
 * Публикация мгновенная, очереди на проверку нет: человек, который
 * ищет работу, не должен ждать сутки. Поэтому раздел — не конвейер,
 * а место, куда приходят по жалобе или после беглого просмотра.
 */
class ResumeResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'resumes';

    protected static ?string $model = Resume::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedIdentification;

    protected static ?string $navigationLabel = 'Резюме';

    protected static ?string $modelLabel = 'резюме';

    protected static ?string $pluralModelLabel = 'резюме';

    protected static string|UnitEnum|null $navigationGroup = 'Модерация';

    protected static ?int $navigationSort = 3;

    public static function table(Table $table): Table
    {
        return ResumesTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListResumes::route('/'),
        ];
    }
}
