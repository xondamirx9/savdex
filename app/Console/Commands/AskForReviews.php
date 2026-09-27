<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\User;
use App\Models\UserNotification;
use App\Support\Notifier;
use Illuminate\Console\Command;
use Illuminate\Database\Eloquent\Builder;

/**
 * Просьбы оставить отзыв — в колокольчик, по одной на повод.
 *
 * Отзывы на площадке пишут только сами пользователи, и без напоминания
 * их почти не пишут: довольный покупатель просто идёт дальше. Поэтому
 * площадка спрашивает сама, но один раз и в подходящий момент:
 *
 * - о площадке — через неделю после регистрации, когда человек уже
 *   что-то успел сделать, а не в первый же день;
 * - о компании — через три дня после раскрытия её контактов: к этому
 *   времени обычно понятно, как прошёл разговор. Позже месяца уже не
 *   спрашиваем — впечатление стёрлось.
 *
 * Повтор отсекается по уже отправленному уведомлению того же вида:
 * отдельная таблица «кого спросили» не нужна. Кто уже написал отзыв,
 * просьбу не получает.
 */
class AskForReviews extends Command
{
    protected $signature = 'reviews:ask {--limit=300 : Сколько просьб каждого вида за один запуск}';

    protected $description = 'Попросить пользователей оставить отзыв о площадке и о компаниях, с которыми они связались';

    public const TYPE_PLATFORM = 'platform_review_ask';

    public const TYPE_COMPANY = 'review_ask';

    public const PLATFORM_AFTER_DAYS = 7;

    public const COMPANY_AFTER_DAYS = 3;

    public const COMPANY_WITHIN_DAYS = 30;

    public function handle(Notifier $notifier): int
    {
        $limit = max(1, (int) $this->option('limit'));
        $platform = $this->askAboutPlatform($notifier, $limit);
        $companies = $this->askAboutCompanies($notifier, $limit);

        $this->info("Просьб о площадке: {$platform}, о компаниях: {$companies}.");

        return self::SUCCESS;
    }

    private function askAboutPlatform(Notifier $notifier, int $limit): int
    {
        $users = User::query()
            ->where('status', 'active')
            ->where('is_admin', false)
            ->whereNotNull('email_verified_at')
            ->where('created_at', '<=', now()->subDays(self::PLATFORM_AFTER_DAYS))
            ->whereNotExists(fn ($q) => $q->selectRaw('1')->from('platform_reviews')->whereColumn('platform_reviews.user_id', 'users.id'))
            ->whereNotExists(fn ($q) => $q->selectRaw('1')->from('user_notifications')
                ->whereColumn('user_notifications.user_id', 'users.id')
                ->where('user_notifications.type', self::TYPE_PLATFORM))
            ->orderBy('id')
            ->limit($limit)
            ->get();

        foreach ($users as $user) {
            $notifier->user($user, self::TYPE_PLATFORM, __('ui.platform_reviews.ask_title', locale: $user->locale), [
                'tone' => 'info',
                'body' => __('ui.platform_reviews.ask_body', locale: $user->locale),
                'url' => '/reviews/new',
            ]);
        }

        return $users->count();
    }

    /**
     * Раскрытия контактов, после которых можно попросить отзыв.
     *
     * Условия те же, что у самой формы отзыва (ReviewService): раскрыл
     * контакты, компания жива, отзыва от его компании ещё нет. Жалоба
     * на контакты — не повод спрашивать про сотрудничество.
     */
    private function askAboutCompanies(Notifier $notifier, int $limit): int
    {
        $unlocks = ContactUnlock::query()
            ->with(['user', 'targetCompany'])
            ->whereNotNull('user_id')
            ->whereNull('complaint_status')
            ->whereBetween('created_at', [now()->subDays(self::COMPANY_WITHIN_DAYS), now()->subDays(self::COMPANY_AFTER_DAYS)])
            ->whereHas('targetCompany', fn (Builder $q) => $q->where('status', Company::STATUS_ACTIVE))
            ->whereHas('user', fn (Builder $q) => $q->where('status', 'active'))
            ->whereNotExists(fn ($q) => $q->selectRaw('1')->from('reviews')
                ->whereColumn('reviews.company_id', 'contact_unlocks.target_company_id')
                ->whereColumn('reviews.author_company_id', 'contact_unlocks.company_id'))
            ->orderBy('id')
            ->get();

        $sent = 0;

        foreach ($unlocks->unique(fn (ContactUnlock $u): string => $u->user_id.':'.$u->target_company_id) as $unlock) {
            if ($sent >= $limit) {
                break;
            }

            $user = $unlock->user;
            $url = '/company/'.$unlock->targetCompany->slug.'#reviews';

            $asked = UserNotification::query()
                ->where('user_id', $user->id)
                ->where('type', self::TYPE_COMPANY)
                ->where('url', $url)
                ->exists();

            if ($asked) {
                continue;
            }

            $notifier->user($user, self::TYPE_COMPANY, __('ui.platform_reviews.ask_company_title', ['name' => $unlock->targetCompany->name], $user->locale), [
                'tone' => 'info',
                'body' => __('ui.platform_reviews.ask_company_body', locale: $user->locale),
                'url' => $url,
            ]);
            $sent++;
        }

        return $sent;
    }
}
