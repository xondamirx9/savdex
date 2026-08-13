<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\User;
use App\Models\Wallet;
use App\Support\Notifier;
use App\Support\StatsRecorder;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Support\Facades\DB;

/**
 * Раскрытие контактов компании за кредит — ядро монетизации (§3.2 ТЗ).
 *
 * Вынесено в сервис, а не в контроллер: операция затрагивает пять
 * таблиц (раскрытие, кошелёк, история движений, статистика, события)
 * и должна быть атомарной целиком. Частично выполненное раскрытие —
 * это либо списанный кредит без доступа, либо доступ без списания.
 *
 * Правила, которые здесь закреплены:
 * — платят за компанию, а не за объявление: открыв контакт по одному
 *   объявлению, покупатель видит его во всех остальных и навсегда;
 * — повторное раскрытие не списывает ничего;
 * — свои контакты не покупают;
 * — израсходованные контакты считаются по месячному лимиту тарифа,
 *   а кредиты тратятся сверх него.
 */
class ContactUnlockService
{
    public function __construct(
        private readonly Notifier $notifier,
        private readonly StatsRecorder $stats,
    ) {}

    /**
     * Результат попытки раскрытия.
     *
     * @return array{ok: bool, message: string, unlock: ContactUnlock|null}
     */
    public function unlock(User $user, Company $target, ?Listing $listing = null): array
    {
        $company = $user->company;

        if ($company === null) {
            return $this->fail('Сначала заполните данные компании — раскрытие идёт от её имени.');
        }

        if ($company->id === $target->id) {
            return $this->fail('Это контакты вашей компании.');
        }

        /*
         * Причина отказа называется точно.
         *
         * Раньше здесь стояла одна проверка canAct() с сообщением про
         * почту — и человек с подтверждённой почтой, но заблокированной
         * компанией, читал совет, который ему не поможет.
         */
        if (! $user->hasVerifiedEmail()) {
            return $this->fail('Подтвердите почту, чтобы открывать контакты.');
        }

        if ($user->must_change_password) {
            return $this->fail('Смените выданный пароль на свой — после этого раскрытие станет доступно.');
        }

        if ($user->status !== 'active') {
            return $this->fail('Ваша учётная запись заблокирована. Напишите в поддержку.');
        }

        if ($company->isBlocked()) {
            return $this->fail('Ваша компания заблокирована, раскрытие контактов недоступно.');
        }

        if ($target->isBlocked()) {
            return $this->fail('Компания заблокирована, её контакты недоступны.');
        }

        // Уже открыт — повторно не списываем. Это обещание витрины:
        // «заплатили один раз и навсегда»
        $existing = ContactUnlock::query()
            ->where('company_id', $company->id)
            ->where('target_company_id', $target->id)
            ->first();

        if ($existing !== null) {
            return [
                'ok' => true,
                'message' => 'Контакты этой компании у вас уже открыты.',
                'unlock' => $existing,
            ];
        }

        return $this->charge($user, $company, $target, $listing);
    }

    /**
     * @return array{ok: bool, message: string, unlock: ContactUnlock|null}
     */
    private function charge(User $user, Company $company, Company $target, ?Listing $listing): array
    {
        $plan = $company->plan();
        $wallet = $company->wallet;

        if ($wallet === null) {
            return $this->fail('Кошелёк компании не найден. Напишите в поддержку.');
        }

        /*
         * Остаток лимита читается под блокировкой строки кошелька и
         * внутри той же транзакции, что и списание.
         *
         * Раньше решение «укладываемся в лимит» принималось до
         * транзакции, по незаблокированной строке: два одновременных
         * раскрытия на последнем слоте оба видели остаток и оба его
         * расходовали — один контакт уходил бесплатно.
         *
         * Порядок расхода остался прежним: сначала месячный лимит
         * тарифа, и только когда он исчерпан — кредиты. Обратный
         * съедал бы купленные кредиты при неиспользованном лимите,
         * за который уже заплачено подпиской.
         */
        try {
            $unlock = DB::transaction(function () use ($user, $company, $target, $listing, $wallet, $plan) {
                $locked = Wallet::query()->lockForUpdate()->find($wallet->id);

                if ($locked === null) {
                    return null;
                }

                $withinPlanLimit = $plan->contacts_limit === null
                    || $locked->contacts_used_this_period < $plan->contacts_limit;

                if ($withinPlanLimit) {
                    $locked->increment('contacts_used_this_period');
                    $creditsSpent = 0;
                } else {
                    // spend() ведёт двойную запись и блокирует ту же строку
                    // повторно — внутри нашей транзакции это уже наш замок
                    if (! $locked->spend('credits', 1, 'unlock', $target, $user->id)) {
                        return null;
                    }

                    $creditsSpent = 1;
                }

                return ContactUnlock::create([
                    'company_id' => $company->id,
                    'target_company_id' => $target->id,
                    'user_id' => $user->id,
                    'listing_id' => $listing?->id,
                    'credits_spent' => $creditsSpent,
                    'status' => 'new',
                ]);
            });
        } catch (UniqueConstraintViolationException) {
            /*
             * Гонка: два одновременных раскрытия одной и той же компании.
             * Проверка «уже открыт» шла до транзакции, поэтому оба доходили
             * сюда; блокировка кошелька сериализует списание, но второй
             * INSERT упирается в unique(company_id, target_company_id) —
             * транзакция откатывается целиком (списание тоже), и мы просто
             * отдаём уже открытые контакты вместо ошибки 500.
             */
            $existing = ContactUnlock::query()
                ->where('company_id', $company->id)
                ->where('target_company_id', $target->id)
                ->first();

            if ($existing !== null) {
                return [
                    'ok' => true,
                    'message' => 'Контакты этой компании у вас уже открыты.',
                    'unlock' => $existing,
                ];
            }

            throw new \RuntimeException('Не удалось открыть контакты, попробуйте ещё раз.');
        }

        if ($unlock === null) {
            $resets = $wallet->period_resets_at?->translatedFormat('d.m.Y');

            return $this->fail(
                'Лимит контактов по тарифу исчерпан, кредитов на счету нет.'
                .($resets !== null ? " Лимит обновится {$resets}." : '')
                .' Купите пакет кредитов или смените тариф.',
            );
        }

        $this->afterUnlock($company, $target, $listing);

        return [
            'ok' => true,
            'message' => 'Контакты открыты. Доступ сохраняется навсегда — платить второй раз за эту компанию не нужно.',
            'unlock' => $unlock,
        ];
    }

    /**
     * Побочные эффекты вне денежной транзакции.
     *
     * Специально снаружи: статистика и уведомления не должны откатывать
     * оплаченное раскрытие, если, например, упадёт отправка уведомления.
     */
    private function afterUnlock(Company $company, Company $target, ?Listing $listing): void
    {
        if ($listing !== null) {
            $this->stats->unlock($listing);
        }

        $this->notifier->company(
            $target,
            'contact_unlocked',
            "Компания «{$company->name}» открыла ваши контакты",
            [
                'tone' => 'success',
                'body' => $listing !== null
                    ? "По объявлению «{$listing->title}». Это тёплый лид: за контакт заплатили."
                    : 'Это тёплый лид: за контакт заплатили.',
                'url' => '/cabinet/incoming',
            ],
        );
    }

    /** @return array{ok: bool, message: string, unlock: null} */
    private function fail(string $message): array
    {
        return ['ok' => false, 'message' => $message, 'unlock' => null];
    }
}
