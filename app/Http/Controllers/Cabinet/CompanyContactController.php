<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\CompanyContact;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

/**
 * Контакты компании: телефоны, почты, мессенджеры, сайт.
 *
 * Это товар площадки — то, за что платят кредитами. До появления
 * этого контроллера завести контакт можно было только через сидер:
 * форма профиля их не принимала, отдельного экрана не существовало.
 * Из-за этого же заполненность профиля не могла достичь 100 %.
 */
class CompanyContactController extends Controller
{
    public function store(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null) {
            return back()->with('error', 'Сначала заполните данные компании');
        }

        $data = $this->validated($request);

        /*
         * Дубликат не создаём, а обновляем: один и тот же номер,
         * добавленный дважды, выглядит на визитке как небрежность
         * и раздувает счётчик скрытых контактов.
         */
        $contact = $company->contacts()->firstOrNew([
            'type' => $data['type'],
            'value' => $data['value'],
        ]);

        $wasNew = ! $contact->exists;

        $contact->fill([
            'label' => $data['label'] ?? null,
            'contact_person' => $data['contact_person'] ?? null,
            'is_public' => $request->boolean('is_public', true),
            'sort_order' => $data['sort_order'] ?? $company->contacts()->count(),
        ]);

        // Первый контакт своего типа становится основным
        $contact->is_primary = $contact->is_primary
            ?? ! $company->contacts()->where('type', $data['type'])->where('is_primary', true)->exists();

        $contact->save();

        return back()->with('success', $wasNew ? 'Контакт добавлен' : 'Контакт обновлён');
    }

    public function update(Request $request, int $id): RedirectResponse
    {
        $contact = $this->owned($request, $id);

        $contact->fill($this->validated($request, $contact->id))->save();

        return back()->with('success', 'Контакт обновлён');
    }

    public function destroy(Request $request, int $id): RedirectResponse
    {
        $contact = $this->owned($request, $id);
        $company = $request->user()->company;

        /*
         * Последний способ связи удалить нельзя: компания без контактов
         * не может быть найдена, а её объявления теряют смысл. Лучше
         * объяснить это здесь, чем разбирать потом жалобу «мне никто
         * не звонит».
         */
        $remaining = $company->contacts()
            ->whereIn('type', [CompanyContact::TYPE_PHONE, CompanyContact::TYPE_EMAIL])
            ->where('id', '!=', $contact->id)
            ->count();

        if ($remaining === 0 && in_array($contact->type, [CompanyContact::TYPE_PHONE, CompanyContact::TYPE_EMAIL], true)) {
            return back()->with('error', 'Это последний способ связи. Добавьте другой телефон или почту, прежде чем удалять этот.');
        }

        $contact->delete();

        return back()->with('success', 'Контакт удалён');
    }

    /** @return array<string, mixed> */
    private function validated(Request $request, ?int $ignoreId = null): array
    {
        $type = $request->string('type')->toString();

        return $request->validate([
            'type' => ['required', Rule::in(array_keys(CompanyContact::TYPES))],

            // Правило проверки зависит от типа: телефон и почта
            // ошибаются по-разному, и сообщение должно это учитывать
            'value' => [
                'required',
                'string',
                'max:190',
                match ($type) {
                    CompanyContact::TYPE_EMAIL => 'email:rfc',
                    CompanyContact::TYPE_PHONE => 'regex:/^\+?\d[\d\s\-()]{8,17}$/',
                    default => 'string',
                },
                Rule::unique('company_contacts')
                    ->where('company_id', $request->user()->company_id)
                    ->ignore($ignoreId),
            ],

            'label' => ['nullable', 'string', 'max:60'],
            'contact_person' => ['nullable', 'string', 'max:120'],
            'is_public' => ['boolean'],
            'sort_order' => ['nullable', 'integer', 'min:0', 'max:99'],
        ], [
            'value.required' => 'Введите значение контакта',
            'value.email' => 'Проверьте адрес: нужен формат name@company.uz',
            'value.regex' => 'Номер должен содержать от 9 до 15 цифр. Например: +998 90 123-45-67',
            'value.unique' => 'Такой контакт у компании уже есть',
        ]);
    }

    private function owned(Request $request, int $id): CompanyContact
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $contact = $company->contacts()->find($id);

        abort_if($contact === null, 404);

        return $contact;
    }
}
