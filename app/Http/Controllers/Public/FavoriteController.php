<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\Favorite;
use App\Models\Listing;
use App\Support\ListingCard;
use App\Support\StatsRecorder;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Избранные объявления.
 *
 * Таблица favorites заведена вместе с contact_unlocks (шаг воронки
 * между просмотром и раскрытием контакта), но интерфейса у неё
 * не было: сердечко на карточке появилось вместе с новой витриной.
 */
class FavoriteController extends Controller
{
    public function __construct(private readonly StatsRecorder $stats) {}

    public function index(Request $request): Response
    {
        /*
         * Истёкшее или архивное объявление остаётся в списке с пометкой
         * «не активно»: молча выбрасывать сохранённое — значит заставить
         * человека гадать, куда оно делось. Черновики, модерация и
         * отклонённые скрываются целиком: их текст мог измениться или
         * не пройти проверку, показывать его посторонним нельзя.
         */
        $listings = Listing::query()
            ->with(ListingCard::relations())
            ->whereIn('status', [Listing::STATUS_ACTIVE, Listing::STATUS_EXPIRED, Listing::STATUS_ARCHIVED])
            ->whereIn('id', Favorite::query()
                ->where('user_id', $request->user()->id)
                ->pluck('listing_id'))
            ->orderByDesc('published_at')
            ->get()
            ->map(fn (Listing $l): array => [
                ...ListingCard::present($l),
                'active' => $l->status === Listing::STATUS_ACTIVE,
            ]);

        return Inertia::render('Favorites', ['items' => $listings]);
    }

    /**
     * Добавить или убрать объявление из избранного.
     *
     * Один маршрут на оба действия: сердечко — переключатель,
     * и два адреса означали бы рассинхрон состояния на клиенте.
     *
     * Сначала пробуем удалить: снять из избранного можно любое
     * объявление, в том числе снятое с публикации — иначе истёкшая
     * карточка зависала бы в списке навсегда. Проверка статуса
     * нужна только при добавлении.
     *
     * Без check-then-act: удаление и вставка сами по себе атомарны,
     * а двойной клик по сердечку не должен ронять запрос на
     * уникальном индексе — поэтому insertOrIgnore.
     */
    public function toggle(Request $request, int $id): RedirectResponse
    {
        $userId = $request->user()->id;

        $deleted = Favorite::query()
            ->where('user_id', $userId)
            ->where('listing_id', $id)
            ->delete();

        if ($deleted > 0) {
            // Счётчик не уходит в минус даже при рассинхроне
            Listing::withTrashed()
                ->where('id', $id)
                ->where('favorites_count', '>', 0)
                ->decrement('favorites_count');

            return back();
        }

        $listing = Listing::query()
            ->where('id', $id)
            ->where('status', Listing::STATUS_ACTIVE)
            ->firstOrFail();

        $added = Favorite::query()->insertOrIgnore([
            'user_id' => $userId,
            'listing_id' => $listing->id,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        // Счётчик и дневная статистика — только если строка реально
        // вставилась: параллельный двойной клик засчитывается один раз
        if ($added > 0) {
            $this->stats->favorite($listing);
        }

        return back();
    }
}
