<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Filament\Resources\NewsPosts\NewsPostResource;
use App\Filament\Resources\Pages\PageResource;
use App\Models\NewsPost;
use App\Models\Page;
use App\Support\AdminAccess;
use Filament\Widgets\StatsOverviewWidget;
use Filament\Widgets\StatsOverviewWidget\Stat;

/**
 * Недоделанное в контенте — стартовый экран контент-менеджера.
 *
 * Черновики и запланированное к выходу. Опубликованное считать незачем:
 * оно уже работает и внимания не требует.
 */
class ContentDrafts extends StatsOverviewWidget
{
    protected ?string $heading = 'Контент в работе';

    protected static ?int $sort = -26;

    public static function canView(): bool
    {
        return AdminAccess::allows('content.edit');
    }

    protected function getStats(): array
    {
        $drafts = NewsPost::where('is_published', false)->count();
        $scheduled = NewsPost::where('is_published', true)
            ->whereNotNull('published_at')
            ->where('published_at', '>', now())
            ->count();
        $hiddenPages = Page::where('is_published', false)->count();

        return [
            Stat::make('Черновики новостей', (string) $drafts)
                ->icon('heroicon-o-pencil-square')
                ->description($drafts > 0 ? 'ждут публикации' : 'всё опубликовано')
                ->color($drafts > 0 ? 'warning' : 'success')
                ->url(NewsPostResource::getUrl()),

            Stat::make('Выйдут по расписанию', (string) $scheduled)
                ->icon('heroicon-o-calendar')
                // Опубликованная новость с будущей датой ещё не видна
                // читателю: это третье состояние, а не второе
                ->description($scheduled > 0 ? 'уже назначены' : 'ничего не запланировано')
                ->color('info')
                ->url(NewsPostResource::getUrl()),

            Stat::make('Скрытые страницы', (string) $hiddenPages)
                ->icon('heroicon-o-document')
                ->description($hiddenPages > 0 ? 'не видны посетителям' : 'все страницы открыты')
                ->color($hiddenPages > 0 ? 'gray' : 'success')
                ->url(PageResource::getUrl()),
        ];
    }
}
