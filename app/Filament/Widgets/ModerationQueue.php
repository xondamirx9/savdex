<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Filament\Pages\Complaints;
use App\Filament\Resources\CompanyDocuments\CompanyDocumentResource;
use App\Filament\Resources\Listings\ListingResource;
use App\Filament\Resources\Reviews\ReviewResource;
use App\Models\CompanyDocument;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\Review;
use App\Support\AdminAccess;
use Filament\Widgets\StatsOverviewWidget;
use Filament\Widgets\StatsOverviewWidget\Stat;
use Illuminate\Support\Carbon;

/**
 * Очередь на проверку — стартовый экран модератора.
 *
 * Разбивка по типам, а не общий счётчик: «сорок семь на проверке»
 * не говорит, с чего начинать, а «тридцать объявлений и один документ»
 * говорит.
 *
 * Под каждым числом — возраст самого старого. Обещанный срок проверки
 * два часа, и важно не сколько всего накопилось, а сколько ждёт тот,
 * кто ждёт дольше всех.
 */
class ModerationQueue extends StatsOverviewWidget
{
    protected ?string $heading = 'Очередь на проверку';

    protected static ?int $sort = -28;

    public static function canView(): bool
    {
        return AdminAccess::allows('listings.moderate')
            || AdminAccess::allows('documents.moderate')
            || AdminAccess::allows('reviews.moderate');
    }

    protected function getStats(): array
    {
        $stats = [];

        if (AdminAccess::allows('listings.moderate')) {
            $stats[] = $this->queue(
                'Объявления',
                Listing::where('status', Listing::STATUS_MODERATION)->count(),
                Listing::where('status', Listing::STATUS_MODERATION)->min('updated_at'),
                'heroicon-o-rectangle-stack',
                ListingResource::getUrl(),
            );
        }

        if (AdminAccess::allows('documents.moderate')) {
            $stats[] = $this->queue(
                'Документы',
                CompanyDocument::where('moderation_status', 'pending')->count(),
                CompanyDocument::where('moderation_status', 'pending')->min('created_at'),
                'heroicon-o-document-check',
                CompanyDocumentResource::getUrl(),
            );
        }

        if (AdminAccess::allows('reviews.moderate')) {
            $stats[] = $this->queue(
                'Споры по отзывам',
                Review::where('dispute_status', 'pending')->count(),
                Review::where('dispute_status', 'pending')->min('updated_at'),
                'heroicon-o-chat-bubble-left-right',
                ReviewResource::getUrl(),
            );
        }

        if (AdminAccess::allows('complaints.moderate')) {
            $stats[] = $this->queue(
                'Жалобы на контакты',
                ContactUnlock::where('complaint_status', 'pending')->count(),
                ContactUnlock::where('complaint_status', 'pending')->min('complained_at'),
                'heroicon-o-exclamation-triangle',
                Complaints::getUrl(),
            );
        }

        return $stats;
    }

    /** Число, возраст самого старого и ссылка в раздел. */
    private function queue(string $label, int $count, mixed $oldest, string $icon, string $url): Stat
    {
        $stat = Stat::make($label, (string) $count)->icon($icon)->url($url);

        if ($count === 0) {
            return $stat->description('очередь пуста')->color('success');
        }

        $waiting = $oldest !== null ? Carbon::parse($oldest) : null;

        return $stat
            ->description($waiting !== null
                ? 'самое старое ждёт '.$waiting->diffForHumans(syntax: true)
                : 'ждут решения')
            // Два часа — обещанный площадкой срок проверки
            ->color($waiting !== null && $waiting->diffInHours() >= 2 ? 'danger' : 'warning');
    }
}
