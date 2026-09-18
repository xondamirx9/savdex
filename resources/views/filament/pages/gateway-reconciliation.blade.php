{{--
    Сверка со шлюзом.

    Расхождения сгруппированы по видам и отсортированы по срочности:
    одна строка «деньги взяли и не начислили» важнее сотни «закрыт без
    транзакции», и искать её пролистыванием человек не должен.
--}}
<x-filament-panels::page>
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

    @if ($total === 0)
        <x-filament::section>
            <div class="py-8 text-center">
                <p class="text-lg font-medium text-success-600 dark:text-success-400">Расхождений нет</p>
                <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    За выбранный период площадка и шлюз говорят одно и то же.
                </p>
            </div>
        </x-filament::section>
    @else
        @foreach ($kinds as $kind => $meta)
            @php $rows = $grouped[$kind] ?? collect(); @endphp

            @continue($rows->isEmpty())

            <x-filament::section>
                <x-slot name="heading">
                    <span class="flex items-center gap-2">
                        {{ $meta['title'] }}
                        <x-filament::badge :color="$meta['severity']">{{ $rows->count() }}</x-filament::badge>
                    </span>
                </x-slot>

                <x-slot name="description">{{ $meta['hint'] }}</x-slot>

                <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                        <thead class="text-left text-gray-500 dark:text-gray-400">
                            <tr>
                                <th class="py-2 pr-4">Счёт</th>
                                <th class="py-2 pr-4">Компания</th>
                                <th class="py-2 pr-4">Заведён</th>
                                <th class="py-2 pr-4 text-right">У площадки</th>
                                <th class="py-2 pr-4 text-right">У шлюза</th>
                                <th class="py-2">Примечание</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y dark:divide-gray-700">
                            @foreach ($rows as $row)
                                <tr>
                                    <td class="py-2 pr-4 font-medium">{{ $row['number'] ?? '—' }}</td>
                                    <td class="py-2 pr-4">{{ $row['company'] ?? '—' }}</td>
                                    <td class="py-2 pr-4 whitespace-nowrap">
                                        {{ $row['at']?->format('d.m.Y') ?? '—' }}
                                    </td>
                                    <td class="py-2 pr-4 text-right tabular-nums">
                                        {{ $row['ours'] !== null ? number_format($row['ours'], 0, ',', ' ').' '.($row['currency'] === 'UZS' ? 'сум' : $row['currency']) : '—' }}
                                    </td>
                                    <td class="py-2 pr-4 text-right tabular-nums">
                                        {{--
                                            Сторона шлюза хранится в тийинах. Копейки
                                            показываются, только если они есть: округлив
                                            их всегда, мы бы вывели две одинаковые суммы
                                            в строке, которая помечена как расхождение,
                                            и человек решил бы, что ошибается экран.
                                        --}}
                                        @if ($row['theirs'] === null)
                                            —
                                        @else
                                            {{ number_format($row['theirs'] / 100, $row['theirs'] % 100 === 0 ? 0 : 2, ',', ' ') }}
                                            {{ $row['currency'] === 'UZS' ? 'сум' : $row['currency'] }}
                                        @endif
                                    </td>
                                    <td class="py-2 text-gray-500 dark:text-gray-400">{{ $row['note'] ?? '' }}</td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                </div>
            </x-filament::section>
        @endforeach
    @endif
</x-filament-panels::page>
