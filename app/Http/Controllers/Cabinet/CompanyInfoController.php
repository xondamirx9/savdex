<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Models\ItTask;
use App\Models\Support\Message;
use App\Models\Support\Ticket;
use Illuminate\Contracts\Validation\Validator as ValidatorContract;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Validator;

/**
 * Данные компании в настройках профиля.
 *
 * Заполненные сведения (название, ИНН, страна, адрес…) меняются только
 * здесь и раз в полгода — Company::PROFILE_COOLDOWN_MONTHS. Пока срок не
 * вышел, владелец может написать в поддержку: обращение уходит в раздел
 * «Обращения» админки.
 *
 * Отдельные адреса с ответом JSON, а не свойства страницы настроек:
 * саму страницу на боевом отдаёт Django, и блок не должен зависеть
 * от того, какая половина её нарисовала.
 */
class CompanyInfoController extends Controller
{
    public function show(Request $request): JsonResponse
    {
        $company = $this->company($request);

        return response()->json($this->payload($company));
    }

    public function update(Request $request): JsonResponse
    {
        $company = $this->company($request);

        $rules = Arr::only(
            CompanyProfileController::rules($request),
            [...Company::PROFILE_FIELDS, 'it_specializations.*'],
        );
        $validator = Validator::make($request->all(), $rules, CompanyProfileController::messages());

        if ($validator->fails()) {
            return $this->invalid($validator);
        }

        $data = $validator->validated();

        $changed = $company->changedProfileFields($data);
        $until = $company->profileLockedUntil();

        if ($changed !== [] && $until !== null) {
            return response()->json([
                'message' => __('ui.cabinet.settings.company_locked', ['date' => $until->translatedFormat('d.m.Y')]),
                'errors' => array_fill_keys($changed, [__('ui.cabinet.settings.company_locked_field')]),
            ], 422);
        }

        $company->fill($data);

        // Отсчёт полугода — только от смены заполненного; заполнить
        // пустое можно сколько угодно раз
        if ($changed !== []) {
            $company->profile_changed_at = now();
        }

        $company->save();

        return response()->json([
            ...$this->payload($company->refresh()),
            'message' => __('ui.messages.company.saved'),
        ]);
    }

    /**
     * Обращение в поддержку, пока смена недоступна.
     *
     * В обращение сразу попадают компания и дата, до которой действует
     * ограничение: сотруднику не нужно их выяснять.
     */
    public function support(Request $request): JsonResponse
    {
        $company = $this->company($request);
        $user = $request->user();

        $validator = Validator::make($request->all(), [
            'message' => ['required', 'string', 'min:10', 'max:3000'],
        ], [
            'message.required' => __('ui.cabinet.settings.company_support_required'),
            'message.min' => __('ui.cabinet.settings.company_support_short'),
        ]);

        if ($validator->fails()) {
            return $this->invalid($validator);
        }

        $data = $validator->validated();

        $until = $company->profileLockedUntil();

        DB::transaction(function () use ($company, $user, $data, $until): void {
            $ticket = Ticket::create([
                'subject' => mb_substr('Смена данных компании: '.$company->name, 0, 200),
                'user_id' => $user->id,
                'company_id' => $company->id,
                'author_name' => $user->name,
                'author_email' => $user->email,
                'status' => Ticket::STATUS_OPEN,
                'channel' => 'form',
                'priority' => 'normal',
                'last_reply_at' => now(),
            ]);

            Message::create([
                'ticket_id' => $ticket->id,
                'author_id' => $user->id,
                'from_staff' => false,
                'is_internal' => false,
                'body' => $data['message']
                    ."\n\n— Компания #{$company->id} «{$company->name}»"
                    .($until !== null ? ', смена данных доступна с '.$until->format('d.m.Y') : ''),
            ]);
        });

        return response()->json(['message' => __('ui.cabinet.settings.company_support_sent')]);
    }

    /**
     * Ошибки проверки — ответом 422 с JSON.
     *
     * $request->validate() здесь не годится: вне /api Laravel отвечает на
     * ошибку переадресацией назад, и fetch получил бы HTML страницы.
     */
    private function invalid(ValidatorContract $validator): JsonResponse
    {
        return response()->json([
            'message' => $validator->errors()->first(),
            'errors' => $validator->errors()->toArray(),
        ], 422);
    }

    /** Компания владельца; сотрудник и пользователь без компании сюда не пускаются. */
    private function company(Request $request): Company
    {
        $user = $request->user();
        $company = $user->company;

        abort_if($company === null || $user->company_role !== 'owner', 403);

        return $company;
    }

    /** @return array<string, mixed> */
    private function payload(Company $company): array
    {
        $until = $company->profileLockedUntil();

        return [
            'company' => [
                'name' => $company->name,
                'legal_name' => $company->legal_name,
                'tin' => $company->tin,
                'country_id' => $company->country_id,
                'city_id' => $company->city_id,
                'address' => $company->address,
                'employees_range' => $company->employees_range,
                'founded_year' => $company->founded_year,
                'type' => $company->type,
                'description' => $company->description,
                'is_it_provider' => (bool) $company->is_it_provider,
                'it_specializations' => $company->it_specializations ?? [],
            ],
            'locked_until' => $until?->translatedFormat('d.m.Y'),
            'changed_at' => $company->profile_changed_at?->translatedFormat('d.m.Y'),
            'cooldown_months' => Company::PROFILE_COOLDOWN_MONTHS,
            // Сколько ждать и какая часть срока прошла — для плашки над формой
            'days_left' => $until !== null ? (int) ceil(now()->diffInSeconds($until) / 86400) : null,
            'cooldown_progress' => $until !== null && $company->profile_changed_at !== null
                ? round(min(1, max(0,
                    $company->profile_changed_at->diffInSeconds(now()) / max(1, $company->profile_changed_at->diffInSeconds($until)),
                )), 3)
                : null,
            // С какого дня откроется следующая смена, если сохранить изменения сейчас
            'next_if_changed' => now()->addMonthsNoOverflow(Company::PROFILE_COOLDOWN_MONTHS)->translatedFormat('d.m.Y'),
            'countries' => Country::listed()
                ->map(fn (Country $c): array => ['id' => $c->id, 'name' => $c->name()])
                ->values(),
            'cities' => City::query()->where('is_active', true)->with('translations')->orderBy('sort')->orderBy('id')->get()
                ->map(fn (City $c): array => ['id' => $c->id, 'name' => $c->name(), 'country_id' => $c->country_id]),
            'serviceTypes' => collect(ItTask::SERVICE_TYPES)
                ->map(fn (string $label, string $code): string => __('ui.it_tasks.types.'.$code))
                ->all(),
        ];
    }
}
