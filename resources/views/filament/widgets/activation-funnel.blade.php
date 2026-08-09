{{--
    Воронка активации и здоровье площадки.

    Шаги идут сверху вниз с долей от регистраций: так видно не только
    «сколько дошло», но и на каком именно шаге теряется больше всего.
--}}
<x-filament-widgets::widget>
    <div class="grid gap-6 xl:grid-cols-2">
        <x-filament::section>
            <x-slot name="heading">Воронка активации</x-slot>
            <x-slot name="description">От регистрации до объявления, которое видно покупателям</x-slot>

            <div class="space-y-3">
                @foreach ($steps as $i => $step)
                    @php
                        // Потери считаем относительно предыдущего шага: доля
                        // от общего числа не показывает, где именно провал
                        $prev = $i > 0 ? $steps[$i - 1]['value'] : null;
                        $drop = $prev !== null && $prev > 0
                            ? (int) round(($prev - $step['value']) / $prev * 100)
                            : null;
                    @endphp

                    <div>
                        <div class="flex items-baseline justify-between gap-3 text-sm">
                            <span class="font-medium text-gray-950 dark:text-white">{{ $step['label'] }}</span>
                            <span class="tabular-nums text-gray-500 dark:text-gray-400">
                                <b class="text-gray-950 dark:text-white">{{ number_format($step['value'], 0, ',', ' ') }}</b>
                                · {{ $step['share'] }} %
                            </span>
                        </div>

                        <div class="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-white/10">
                            <div
                                class="h-full rounded-full bg-primary-600 transition-all"
                                style="width: {{ max($step['share'], 1) }}%"
                            ></div>
                        </div>

                        <div class="mt-1 flex items-baseline justify-between gap-3">
                            <span class="text-xs text-gray-500 dark:text-gray-400">{{ $step['hint'] }}</span>

                            {{-- Провал больше половины на шаге — почти всегда
                                 не «люди такие», а сломанный или непонятный шаг --}}
                            @if ($drop !== null && $drop > 0)
                                <span @class([
                                    'text-xs font-medium tabular-nums',
                                    'text-danger-600 dark:text-danger-400' => $drop >= 50,
                                    'text-warning-600 dark:text-warning-400' => $drop >= 25 && $drop < 50,
                                    'text-gray-500 dark:text-gray-400' => $drop < 25,
                                ])>
                                    −{{ $drop }} % к прошлому шагу
                                </span>
                            @endif
                        </div>
                    </div>
                @endforeach
            </div>
        </x-filament::section>

        <div class="space-y-6">
            <x-filament::section>
                <x-slot name="heading">Здоровье площадки</x-slot>
                <x-slot name="description">Показатели, по которым проблему видно раньше, чем по выручке</x-slot>

                <div class="space-y-4">
                    @foreach ($health as $item)
                        <div class="flex items-start justify-between gap-4">
                            <div class="min-w-0">
                                <div class="text-sm font-medium text-gray-950 dark:text-white">{{ $item['label'] }}</div>
                                <div class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ $item['hint'] }}</div>
                            </div>

                            <x-filament::badge :color="$item['tone']" class="shrink-0">
                                {{ $item['value'] }}
                            </x-filament::badge>
                        </div>
                    @endforeach
                </div>
            </x-filament::section>

            <x-filament::section>
                <x-slot name="heading">Категории по числу активных объявлений</x-slot>
                <x-slot name="description">Где идёт торговля, а где справочник заполнен зря</x-slot>

                @if (empty($categories))
                    <p class="text-sm text-gray-500 dark:text-gray-400">
                        Пока нет опубликованных объявлений с категорией.
                    </p>
                @else
                    @php $max = max(array_column($categories, 'listings')) ?: 1; @endphp

                    <div class="space-y-2.5">
                        @foreach ($categories as $category)
                            <div class="flex items-center gap-3">
                                <span class="w-40 shrink-0 truncate text-sm text-gray-950 dark:text-white">
                                    {{ $category['label'] }}
                                </span>

                                <div class="h-2 flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-white/10">
                                    <div
                                        class="h-full rounded-full bg-primary-500"
                                        style="width: {{ round($category['listings'] / $max * 100) }}%"
                                    ></div>
                                </div>

                                <span class="w-24 shrink-0 text-right text-xs tabular-nums text-gray-500 dark:text-gray-400">
                                    {{ $category['listings'] }} / {{ $category['companies'] }} комп.
                                </span>
                            </div>
                        @endforeach
                    </div>
                @endif
            </x-filament::section>
        </div>
    </div>
</x-filament-widgets::widget>
