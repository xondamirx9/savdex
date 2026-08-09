<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Exceptions\InsufficientUnits;
use App\Http\Controllers\Controller;
use App\Models\Listing;
use App\Models\Promotion;
use App\Models\PromotionType;
use App\Support\Notifier;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Продвижение объявлений.
 *
 * Продвинутые объявления помечаются словом «Продвигается»: выдавать
 * рекламу за органическую выдачу площадка не будет — это принцип,
 * заявленный на витрине.
 */
class PromotionController extends Controller
{
    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/Promo', [
                'active' => [],
                'types' => [],
                'listings' => [],
                'units' => 0,
                'resets_at' => null,
            ]);
        }

        $active = $company->promotions()
            ->with(['listing', 'type'])
            ->where('status', 'active')
            ->latest()
            ->get()
            ->map(fn (Promotion $p): array => [
                'id' => $p->id,
                'listing' => $p->listing?->title,
                'type' => $p->type?->name,
                'badge' => $p->type?->badge,
                'ends_at' => $p->ends_at?->translatedFormat('d.m.Y'),
                'before' => $p->impressions_before,
                'after' => $p->impressions_after,
                'effect' => $p->effect(),
            ]);

        $types = PromotionType::query()
            ->where('is_active', true)
            ->orderBy('sort')
            ->get()
            ->map(fn (PromotionType $t): array => [
                'id' => $t->id,
                'code' => $t->code,
                'name' => $t->name,
                'description' => $t->description,
                'effect_hint' => $t->effect_hint,
                'cost' => $t->cost_units,
                'cost_label' => $t->costLabel(),
                'icon' => $t->icon,
                'slots' => $t->slots,
                'taken' => $t->slots !== null ? $t->takenSlots() : null,
                'available' => $t->hasFreeSlot(),
            ]);

        return Inertia::render('cabinet/Promo', [
            'active' => $active,
            'types' => $types,
            'listings' => $company->activeListings()
                ->get()
                ->map(fn (Listing $l): array => ['id' => $l->id, 'title' => $l->title]),
            'units' => $company->wallet?->promo_units ?? 0,
            'resets_at' => $company->wallet?->period_resets_at?->translatedFormat('d.m.Y'),
        ]);
    }

    public function store(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $data = $request->validate([
            'listing_id' => ['required', 'integer'],
            'promotion_type_id' => ['required', 'exists:promotion_types,id'],
        ], [
            'listing_id.required' => 'Выберите объявление',
        ]);

        $listing = $company->activeListings()->find($data['listing_id']);

        if ($listing === null) {
            return back()->with('error', 'Продвигать можно только активные объявления');
        }

        $type = PromotionType::findOrFail($data['promotion_type_id']);

        // Одно и то же продвижение дважды на одном объявлении —
        // деньги на ветер: второе не усиливает первое
        $duplicate = $company->promotions()
            ->where('listing_id', $listing->id)
            ->where('promotion_type_id', $type->id)
            ->where('status', 'active')
            ->exists();

        if ($duplicate) {
            return back()->with('error', "«{$type->name}» уже действует на этом объявлении");
        }

        if (! $type->hasFreeSlot($listing->category_id)) {
            return back()->with('error', "Все места «{$type->name}» заняты. Освободятся, когда закончится текущее размещение.");
        }

        $wallet = $company->wallet;

        if ($wallet === null) {
            return back()->with('error', 'Кошелёк компании не найден. Напишите в поддержку.');
        }

        /*
         * Списание и запуск — одной транзакцией.
         *
         * Раньше spend() коммитился сам по себе, и падение на создании
         * строки оставляло компанию без единиц и без продвижения.
         *
         * Уникальный индекс на active_key ловит второй одновременный
         * запрос: проверка дубля выше отсекает обычный случай, но между
         * ней и вставкой помещается параллельный запрос, и обещание
         * «дважды одно и то же не продаём» держит только база.
         */
        try {
            DB::transaction(function () use ($company, $listing, $type, $wallet, $request): void {
                if (! $wallet->spend('promo_units', $type->cost_units, 'promotion', $listing, $request->user()->id)) {
                    throw new InsufficientUnits;
                }

                Promotion::create([
                    'listing_id' => $listing->id,
                    'company_id' => $company->id,
                    'promotion_type_id' => $type->id,
                    'category_id' => $listing->category_id,
                    'units_spent' => $type->cost_units,
                    'status' => 'active',
                    'starts_at' => now(),
                    'ends_at' => $type->duration_days > 0 ? now()->addDays($type->duration_days) : null,
                    // Фиксируем базу для честного расчёта эффекта
                    'impressions_before' => $listing->impressions_count,
                ]);
            });
        } catch (InsufficientUnits) {
            return back()->with('error', "Не хватает единиц продвижения: нужно {$type->cost_units}, есть {$wallet->promo_units}");
        } catch (UniqueConstraintViolationException) {
            return back()->with('error', "«{$type->name}» уже действует на этом объявлении");
        }

        app(Notifier::class)->company(
            $company,
            'promotion',
            "Запущено продвижение «{$type->name}» на объявлении «{$listing->title}»",
            ['tone' => 'success', 'url' => route('cabinet.promo')],
        );

        return back()->with('success', "«{$type->name}» запущено. Списано единиц: {$type->cost_units}.");
    }
}
