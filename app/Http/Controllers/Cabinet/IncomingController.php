<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\ContactUnlock;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Кто мной интересуется — компании, открывшие наши контакты.
 *
 * Названия видны только на Business и Premium (§3 ТЗ). На младших
 * тарифах показываются город и тип компании: сам факт интереса —
 * достаточный повод задуматься о тарифе, а имена уже платная часть.
 */
class IncomingController extends Controller
{
    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/Incoming', [
                'rows' => [],
                'sees_names' => false,
                'plan' => null,
            ]);
        }

        $plan = $company->plan();
        $seesNames = (bool) $plan->sees_interested_names;

        $rows = $company->unlockedBy()
            ->with(['company.city.translations', 'listing'])
            ->where('created_at', '>=', now()->subDays(30))
            ->latest()
            ->get()
            ->map(fn (ContactUnlock $u): array => [
                'id' => $u->id,
                // Скрытие делается на сервере: отдать имя и спрятать
                // его в вёрстке значит отдать его совсем
                'name' => $seesNames ? $u->company?->name : null,
                'slug' => $seesNames ? $u->company?->slug : null,
                'initials' => $seesNames ? $u->company?->initials() : null,
                'verified' => (int) ($u->company?->verification_level ?? 0),
                'type' => $u->company?->primary_role === 'buyer' ? 'закупщик' : 'поставщик',
                'rating' => (float) ($u->company?->rating ?? 0),
                'city' => $u->company?->city?->name() ?? 'Не указан',
                'listing' => $u->listing?->title,
                'when' => $u->created_at->diffForHumans(),
            ]);

        return Inertia::render('cabinet/Incoming', [
            'rows' => $rows,
            'sees_names' => $seesNames,
            'plan' => ['name' => $plan->name],
        ]);
    }
}
