<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\Company;
use App\Models\Review;
use App\Services\ReviewService;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Collection;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Отзывы о компании.
 *
 * Удалить отзыв нельзя — только ответить или оспорить через модератора.
 * Возможность стирать неудобные отзывы обесценивает рейтинг целиком.
 */
class ReviewController extends Controller
{
    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/Reviews', [
                'reviews' => [],
                'summary' => null,
                'criteria' => Review::CRITERIA,
            ]);
        }

        $reviews = $company->reviews()
            ->with(['authorCompany', 'listing'])
            ->latest()
            ->get();

        return Inertia::render('cabinet/Reviews', [
            'reviews' => $reviews->map(fn (Review $r): array => [
                'id' => $r->id,
                'author' => $r->authorCompany?->name,
                'initials' => $r->authorCompany?->initials(),
                'verified' => (int) ($r->authorCompany?->verification_level ?? 0),
                'rating' => $r->rating,
                'body' => $r->body,
                'deal_confirmed' => $r->deal_confirmed,
                'listing' => $r->listing?->title,
                'reply' => $r->reply,
                'dispute_status' => $r->dispute_status,
                // Ответ модератора дословно: статус «отклонён» без
                // объяснения читается как отписка
                'moderator_note' => $r->moderator_note,
                'when' => $r->created_at->diffForHumans(),
            ]),
            'summary' => $this->summary($reviews),
            'criteria' => Review::CRITERIA,
        ]);
    }

    /**
     * Средние по критериям и распределение оценок.
     *
     * @param  Collection<int, Review>  $reviews
     * @return array<string, mixed>|null
     */
    private function summary($reviews): ?array
    {
        if ($reviews->isEmpty()) {
            return null;
        }

        /*
         * Список, а не объект с числовыми ключами: JSON-объект с ключами
         * «5», «4», «3» в JavaScript пересортируется по возрастанию,
         * и шкала переворачивается — единицы оказываются сверху.
         *
         * Нули включены намеренно: пропущенная строка «2★» читается
         * как отсутствие данных, хотя это осмысленный ноль.
         */
        $distribution = collect(range(5, 1))
            ->map(fn (int $star): array => [
                'star' => $star,
                'count' => $reviews->where('rating', $star)->count(),
            ])
            ->values()
            ->all();

        $criteria = [];

        foreach (Review::CRITERIA as $key => $label) {
            $values = $reviews->pluck($key)->filter();

            $criteria[] = [
                'label' => $label,
                'value' => $values->isEmpty() ? null : round((float) $values->avg(), 1),
            ];
        }

        return [
            'average' => round((float) $reviews->avg('rating'), 1),
            'total' => $reviews->count(),
            'distribution' => $distribution,
            'criteria' => $criteria,
        ];
    }

    /**
     * Оставить отзыв о компании.
     *
     * Живёт на визитке, а не в кабинете: отзыв пишут там, где смотрят
     * на компанию. Право проверяет ReviewService — платившим за контакт,
     * по одному разу.
     */
    public function store(Request $request, string $slug): RedirectResponse
    {
        $target = Company::where('slug', $slug)->firstOrFail();

        $data = $request->validate(ReviewService::rules(), ReviewService::messages());

        $result = app(ReviewService::class)->create($request->user(), $target, $data);

        return back()->with($result['ok'] ? 'success' : 'error', $result['message']);
    }

    public function reply(Request $request, int $id): RedirectResponse
    {
        $review = $this->owned($request, $id);

        $data = $request->validate([
            'reply' => ['required', 'string', 'min:10', 'max:2000'],
        ], [
            'reply.required' => 'Напишите ответ',
            'reply.min' => 'Ответ слишком короткий',
        ]);

        $review->forceFill([
            'reply' => $data['reply'],
            'replied_at' => now(),
        ])->save();

        return back()->with('success', 'Ответ опубликован');
    }

    public function dispute(Request $request, int $id): RedirectResponse
    {
        $review = $this->owned($request, $id);

        if ($review->dispute_status !== null) {
            return back()->with('error', 'Отзыв уже на рассмотрении');
        }

        $data = $request->validate([
            'reason' => ['required', 'string', 'min:20', 'max:1000'],
        ], [
            'reason.required' => 'Опишите, почему отзыв недостоверен',
            'reason.min' => 'Модератору нужны детали: что именно не соответствует действительности',
        ]);

        $review->forceFill([
            'dispute_status' => 'pending',
            'dispute_reason' => $data['reason'],
        ])->save();

        return back()->with('success', 'Отзыв отправлен на проверку модератору');
    }

    private function owned(Request $request, int $id): Review
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $review = $company->reviews()->find($id);

        abort_if($review === null, 404);

        return $review;
    }
}
