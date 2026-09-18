{{--
    Финансовые отчёты.

    Числа набраны моноширинным: колонка сумм, набранная пропорциональным
    шрифтом, не сравнивается взглядом — приходится читать каждую цифру.
--}}
@php
    $money = fn (int $amount, string $currency): string =>
        number_format($amount, 0, ',', ' ').' '.($currency === 'UZS' ? 'сум' : $currency);
@endphp

<x-filament-panels::page>
    {{-- Период --}}
    <x-filament::section>
        <div class="flex flex-wrap items-end gap-4">
            <div>
                <label class="block text-sm font-medium mb-1" for="from">С</label>
                <input id="from" type="date" wire:model.live="from"
                       class="fi-input block w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-900">
            </div>

            <div>
                <label class="block text-sm font-medium mb-1" for="to">По</label>
                <input id="to" type="date" wire:model.live="to"
                       class="fi-input block w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-900">
            </div>

            <div class="flex flex-wrap gap-2">
                @foreach (['this' => 'Этот месяц', 'prev' => 'Прошлый', 'quarter' => 'Квартал', 'year' => 'Год'] as $key => $label)
                    <x-filament::button wire:click="setPeriod('{{ $key }}')" color="gray" size="sm">
                        {{ $label }}
                    </x-filament::button>
                @endforeach
            </div>
        </div>
    </x-filament::section>

    {{-- Выручка --}}
    <x-filament::section heading="Выручка">
        <x-slot name="description">
            Возвраты вычитаются по дате возврата: деньги ушли из кассы тогда, когда их вернули.
        </x-slot>

        @forelse ($revenue as $currency => $row)
            <div class="grid gap-4 sm:grid-cols-4 {{ ! $loop->first ? 'mt-4 border-t pt-4 dark:border-gray-700' : '' }}">
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">Поступило</div>
                    <div class="text-2xl font-semibold tabular-nums">{{ $money($row['gross'], $currency) }}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">Возвращено</div>
                    <div class="text-2xl font-semibold tabular-nums text-warning-600 dark:text-warning-400">
                        {{ $money($row['refunded'], $currency) }}
                    </div>
                </div>
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">Осталось</div>
                    <div class="text-2xl font-semibold tabular-nums text-success-600 dark:text-success-400">
                        {{ $money($row['net'], $currency) }}
                    </div>
                </div>
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">Оплат</div>
                    <div class="text-2xl font-semibold tabular-nums">{{ $row['count'] }}</div>
                </div>
            </div>
        @empty
            <p class="text-sm text-gray-500 dark:text-gray-400">За выбранный период оплат не было.</p>
        @endforelse
    </x-filament::section>

    {{-- Подписки --}}
    <x-filament::section heading="Продления и отток">
        <x-slot name="description">
            «Истекли без продления» — молчаливый отток: срок вышел, новой подписки нет.
            Он опаснее явного отказа, о нём никто не сообщает.
        </x-slot>

        <div class="grid gap-4 sm:grid-cols-5">
            @foreach ([
                'new' => ['Новые', 'text-success-600 dark:text-success-400'],
                'renewed' => ['Продлили', 'text-success-600 dark:text-success-400'],
                'cancelled' => ['Отказались', 'text-danger-600 dark:text-danger-400'],
                'expired' => ['Истекли без продления', 'text-danger-600 dark:text-danger-400'],
                'active' => ['Действуют на конец', ''],
            ] as $key => [$label, $color])
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">{{ $label }}</div>
                    <div class="text-2xl font-semibold tabular-nums {{ $color }}">{{ $subscriptions[$key] }}</div>
                </div>
            @endforeach
        </div>
    </x-filament::section>

    {{-- По месяцам --}}
    <x-filament::section heading="По месяцам" collapsible>
        <div class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead class="text-left text-gray-500 dark:text-gray-400">
                    <tr>
                        <th class="py-2 pr-4">Месяц</th>
                        <th class="py-2 pr-4 text-right">Поступило</th>
                        <th class="py-2 pr-4 text-right">Возвращено</th>
                        <th class="py-2 pr-4 text-right">Осталось</th>
                        <th class="py-2 text-right">Оплат</th>
                    </tr>
                </thead>
                <tbody class="divide-y dark:divide-gray-700">
                    @foreach ($months as $month)
                        <tr>
                            <td class="py-2 pr-4">{{ $month['label'] }}</td>
                            <td class="py-2 pr-4 text-right tabular-nums">{{ number_format($month['gross'], 0, ',', ' ') }}</td>
                            <td class="py-2 pr-4 text-right tabular-nums">{{ number_format($month['refunded'], 0, ',', ' ') }}</td>
                            <td class="py-2 pr-4 text-right tabular-nums font-medium">{{ number_format($month['net'], 0, ',', ' ') }}</td>
                            <td class="py-2 text-right tabular-nums">{{ $month['count'] }}</td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        </div>
    </x-filament::section>

    <div class="grid gap-6 lg:grid-cols-2">
        {{-- По тарифам --}}
        <x-filament::section heading="По тарифам">
            @if ($plans === [])
                <p class="text-sm text-gray-500 dark:text-gray-400">Оплат за период не было.</p>
            @else
                <table class="w-full text-sm">
                    <thead class="text-left text-gray-500 dark:text-gray-400">
                        <tr>
                            <th class="py-2 pr-4">Тариф</th>
                            <th class="py-2 pr-4 text-right">Оплат</th>
                            <th class="py-2 text-right">Сумма</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y dark:divide-gray-700">
                        @foreach ($plans as $plan)
                            <tr>
                                <td class="py-2 pr-4">{{ $plan['name'] }}</td>
                                <td class="py-2 pr-4 text-right tabular-nums">{{ $plan['count'] }}</td>
                                <td class="py-2 text-right tabular-nums">{{ number_format($plan['gross'], 0, ',', ' ') }}</td>
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            @endif
        </x-filament::section>

        {{-- По источникам --}}
        <x-filament::section heading="По источникам">
            @if ($sources === [])
                <p class="text-sm text-gray-500 dark:text-gray-400">Оплат за период не было.</p>
            @else
                <table class="w-full text-sm">
                    <thead class="text-left text-gray-500 dark:text-gray-400">
                        <tr>
                            <th class="py-2 pr-4">За что</th>
                            <th class="py-2 pr-4">Шлюз</th>
                            <th class="py-2 pr-4 text-right">Оплат</th>
                            <th class="py-2 text-right">Сумма</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y dark:divide-gray-700">
                        @foreach ($sources as $source)
                            <tr>
                                <td class="py-2 pr-4">{{ $source['purpose'] }}</td>
                                <td class="py-2 pr-4">{{ $source['provider'] }}</td>
                                <td class="py-2 pr-4 text-right tabular-nums">{{ $source['count'] }}</td>
                                <td class="py-2 text-right tabular-nums">{{ number_format($source['gross'], 0, ',', ' ') }}</td>
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            @endif
        </x-filament::section>
    </div>
</x-filament-panels::page>
