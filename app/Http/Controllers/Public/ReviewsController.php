<?php

declare(strict_types=1);

namespace App\Http\Controllers\Public;

use App\Http\Controllers\Controller;
use App\Models\PlatformReview;
use App\Services\PlatformReviewService;
use App\Services\ReviewService;
use App\Support\ReviewFeed;
use App\Support\Seo;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

/**
 * «Все отзывы» и форма «Оцените SavdEx».
 *
 * Страницу отзывов отдаёт и Django (python/savdex/web/reviews.py) —
 * здесь она для сверки и для отката. Форма пишет в базу и остаётся
 * за Laravel до переноса кабинета.
 */
class ReviewsController extends Controller
{
    private const MAX_PAGE = 10_000;

    public function index(Request $request): Response
    {
        $type = in_array($request->query('type'), ReviewFeed::TYPES, true) ? $request->query('type') : 'all';
        // Предел — чтобы смещение не вышло за целое у базы на выдуманном адресе
        $page = min(max(1, (int) $request->query('page', 1)), self::MAX_PAGE);
        $total = ReviewFeed::count($type);

        app(Seo::class)
            ->title(__('ui.seo.reviews_title'))
            ->description(__('ui.seo.reviews_description'))
            ->canonical(url('/reviews'));

        return Inertia::render('Reviews', [
            'summary' => ReviewFeed::platformSummary(),
            'counts' => array_combine(ReviewFeed::TYPES, array_map(ReviewFeed::count(...), ReviewFeed::TYPES)),
            'type' => $type,
            'reviews' => ReviewFeed::take($type, ReviewFeed::PER_PAGE, ($page - 1) * ReviewFeed::PER_PAGE),
            'page' => $page,
            'pages' => max(1, (int) ceil($total / ReviewFeed::PER_PAGE)),
        ]);
    }

    public function create(Request $request, PlatformReviewService $service): Response
    {
        $mine = $service->mine($request->user());

        app(Seo::class)->title(__('ui.platform_reviews.title'))->noindex();

        return Inertia::render('reviews/Leave', [
            'review' => $mine === null ? null : [
                'rating' => $mine->rating,
                ...array_map(fn (string $field): int => (int) $mine->{$field}, array_combine(
                    array_keys(PlatformReview::CRITERIA),
                    array_keys(PlatformReview::CRITERIA),
                )),
                'body' => $mine->body,
                'status' => $mine->status,
                'note' => $mine->moderator_note,
            ],
            'blocked' => $service->blockedReason($request->user()),
            'criteria' => PlatformReview::criteriaLabels(),
            'minBody' => PlatformReviewService::MIN_BODY,
        ]);
    }

    public function store(Request $request, PlatformReviewService $service): RedirectResponse
    {
        $data = $request->validate(PlatformReviewService::rules(), ReviewService::messages());
        $result = $service->save($request->user(), $data);

        return back()->with($result['ok'] ? 'success' : 'error', $result['message']);
    }
}
