<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\ContactUnlock;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;
use Symfony\Component\HttpFoundation\StreamedResponse;

/**
 * Мои контакты — компании, чьи контакты открыты за кредиты.
 *
 * Доступ навсегда: кредит списан за компанию один раз, и отбирать
 * купленное нельзя. Это обещание вынесено на витрину.
 */
class ContactController extends Controller
{
    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/Contacts', [
                'contacts' => [],
                'statuses' => ContactUnlock::STATUSES,
                'filters' => ['q' => '', 'status' => ''],
            ]);
        }

        $q = $request->string('q')->toString();
        $status = $request->string('status')->toString();

        $contacts = $company->unlocks()
            ->with(['targetCompany.contacts', 'targetCompany.city.translations', 'listing'])
            ->when($status !== '' && array_key_exists($status, ContactUnlock::STATUSES),
                fn ($query) => $query->where('status', $status))
            ->when($q !== '', function ($query) use ($q): void {
                // Поиск идёт и по заметке: человек ищет «ждём КП»,
                // а не только по названию компании
                $query->where(function ($sub) use ($q): void {
                    $sub->whereHas('targetCompany', fn ($c) => $c->where('name', 'like', "%{$q}%"))
                        ->orWhere('note', 'like', "%{$q}%");
                });
            })
            ->latest()
            ->get()
            ->map(fn (ContactUnlock $u): array => [
                'id' => $u->id,
                'company' => [
                    'name' => $u->targetCompany?->name,
                    'slug' => $u->targetCompany?->slug,
                    'initials' => $u->targetCompany?->initials(),
                    'verified' => (int) ($u->targetCompany?->verification_level ?? 0),
                    'city' => $u->targetCompany?->city?->name(),
                ],
                // Контакты показываются целиком — они оплачены
                'phones' => $u->targetCompany?->contacts
                    ->where('type', 'phone')
                    ->pluck('value')
                    ->values() ?? [],
                'emails' => $u->targetCompany?->contacts
                    ->where('type', 'email')
                    ->pluck('value')
                    ->values() ?? [],
                'listing' => $u->listing?->title,
                'opened_at' => $u->created_at->translatedFormat('d.m.Y'),
                'status' => $u->status,
                'status_label' => $u->statusLabel(),
                'note' => $u->note,
                'can_review' => $u->canBeReviewed(),
                'complaint_status' => $u->complaint_status,
                'moderator_note' => $u->moderator_note,
                'refunded' => $u->refunded,
            ]);

        return Inertia::render('cabinet/Contacts', [
            'contacts' => $contacts,
            'statuses' => ContactUnlock::STATUSES,
            'filters' => ['q' => $q, 'status' => $status],
        ]);
    }

    /** Смена статуса и заметки — работа с контактом как с лидом. */
    public function update(Request $request, int $id): RedirectResponse
    {
        $unlock = $this->owned($request, $id);

        $data = $request->validate([
            'status' => ['nullable', 'in:'.implode(',', array_keys(ContactUnlock::STATUSES))],
            'note' => ['nullable', 'string', 'max:500'],
        ]);

        $unlock->fill($data)->save();

        return back()->with('success', 'Сохранено');
    }

    /**
     * Жалоба на нерабочий контакт.
     *
     * Кредит не возвращается сразу: сначала проверка модератором.
     * Автовозврат превратился бы в способ получать контакты бесплатно.
     */
    public function complain(Request $request, int $id): RedirectResponse
    {
        $unlock = $this->owned($request, $id);

        if ($unlock->complaint_status !== null) {
            return back()->with('error', 'Жалоба уже отправлена и рассматривается');
        }

        $data = $request->validate([
            'reason' => ['required', 'string', 'min:10', 'max:500'],
        ], [
            'reason.required' => 'Опишите, что не так с контактом',
            'reason.min' => 'Слишком коротко — модератору нужны детали для проверки',
        ]);

        $unlock->forceFill([
            'complaint_status' => 'pending',
            'complaint_reason' => $data['reason'],
            'complained_at' => now(),
        ])->save();

        return back()->with('success', 'Жалоба отправлена. Проверим и вернём кредит, если контакт действительно нерабочий.');
    }

    /**
     * Выгрузка в CSV.
     *
     * CSV, а не XLSX: библиотеки для Excel тянут заметный вес ради
     * таблицы из шести колонок, а CSV открывается тем же Excel.
     * BOM в начале обязателен — без него кириллица превращается в кракозябры.
     */
    public function export(Request $request): StreamedResponse
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $rows = $company->unlocks()->with(['targetCompany.contacts', 'listing'])->latest()->get();

        return response()->streamDownload(function () use ($rows): void {
            $out = fopen('php://output', 'wb');

            fwrite($out, "\xEF\xBB\xBF");

            fputcsv($out, ['Компания', 'Телефоны', 'Почта', 'Объявление', 'Открыт', 'Статус', 'Заметка'], ';');

            foreach ($rows as $u) {
                fputcsv($out, [
                    $u->targetCompany?->name,
                    $u->targetCompany?->contacts->where('type', 'phone')->pluck('value')->implode(', '),
                    $u->targetCompany?->contacts->where('type', 'email')->pluck('value')->implode(', '),
                    $u->listing?->title,
                    $u->created_at->format('d.m.Y'),
                    $u->statusLabel(),
                    $u->note,
                ], ';');
            }

            fclose($out);
        }, 'savdex-contacts-'.now()->format('Y-m-d').'.csv', [
            'Content-Type' => 'text/csv; charset=UTF-8',
        ]);
    }

    private function owned(Request $request, int $id): ContactUnlock
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $unlock = $company->unlocks()->find($id);

        abort_if($unlock === null, 404);

        return $unlock;
    }
}
