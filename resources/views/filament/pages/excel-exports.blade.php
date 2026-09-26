{{--
    Выгрузка в Excel: кнопка в шапке, ниже — список выгрузок.

    Пока идёт выгрузка, список обновляется сам раз в пять секунд:
    человек нажал кнопку и ждёт, перезагружать страницу руками он
    не должен.
--}}
<x-filament-panels::page>
    <div @if ($active) wire:poll.5s @endif class="space-y-6">
        @if ($runs === [])
            <x-filament::section>
                <div class="py-8 text-center">
                    <p class="text-lg font-medium">Выгрузок пока нет</p>
                    <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Нажмите «Выгрузить сейчас» — через минуту-другую здесь появятся два файла Excel.
                    </p>
                </div>
            </x-filament::section>
        @else
            <x-filament::section>
                <x-slot name="heading">Последние выгрузки</x-slot>
                <x-slot name="description">
                    Хранятся последние {{ $keep }}; более старые удаляются, чтобы не забить диск.
                </x-slot>

                <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                        <thead class="text-left text-gray-500 dark:text-gray-400">
                            <tr>
                                <th class="py-2 pr-4 font-medium">Когда</th>
                                <th class="py-2 pr-4 font-medium">Кто</th>
                                <th class="py-2 pr-4 font-medium">Состояние</th>
                                <th class="py-2 pr-4 font-medium">Файлы</th>
                                <th class="py-2 font-medium">Сверка с Python</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200 dark:divide-white/10">
                            @foreach ($runs as $run)
                                @php
                                    $status = $run['status'];
                                    $python = $run['python'] ?? null;
                                @endphp
                                <tr class="align-top" data-run="{{ $run['id'] }}">
                                    <td class="py-3 pr-4 whitespace-nowrap">
                                        {{ \App\Filament\Pages\ExcelExports::when($run['queued_at'] ?? null) }}
                                    </td>
                                    <td class="py-3 pr-4">{{ $run['requested_by'] ?? '—' }}</td>
                                    <td class="py-3 pr-4">
                                        @switch($status)
                                            @case('queued')
                                                <x-filament::badge color="gray">в очереди</x-filament::badge>
                                                @break
                                            @case('running')
                                                <x-filament::badge color="warning">идёт…</x-filament::badge>
                                                @break
                                            @case('done')
                                                <x-filament::badge color="success">готово</x-filament::badge>
                                                @break
                                            @default
                                                <x-filament::badge color="danger">ошибка</x-filament::badge>
                                        @endswitch

                                        @if (! empty($run['note']))
                                            <p class="mt-1 text-xs text-gray-500">{{ $run['note'] }}</p>
                                        @endif

                                        @if ($status === 'failed' && ! empty($run['php']['output']))
                                            <details class="mt-1 text-xs text-gray-500">
                                                <summary class="cursor-pointer">подробности</summary>
                                                <pre class="mt-1 whitespace-pre-wrap">{{ $run['php']['output'] }}</pre>
                                            </details>
                                        @endif
                                    </td>
                                    <td class="py-3 pr-4">
                                        @if ($status === 'done' && $canDownload)
                                            <div class="flex flex-col gap-1">
                                                @foreach ($run['php']['files'] ?? [] as $file)
                                                    <x-filament::link
                                                        :href="route('filament.admin.exports.download', ['run' => $run['id'], 'file' => $file])"
                                                        icon="heroicon-o-arrow-down-tray"
                                                    >
                                                        {{ str_contains($file, 'companies') ? 'Компании' : 'Объявления' }}
                                                    </x-filament::link>
                                                @endforeach
                                            </div>
                                        @elseif ($status === 'done')
                                            <span class="text-gray-500">нет права скачивать</span>
                                        @else
                                            <span class="text-gray-500">—</span>
                                        @endif
                                    </td>
                                    <td class="py-3">
                                        @switch($python['status'] ?? null)
                                            @case('match')
                                                <x-filament::badge color="success">совпала</x-filament::badge>
                                                @break
                                            @case('differs')
                                                <x-filament::badge color="danger">
                                                    расходится{{ ! empty($python['differences']) ? ': '.$python['differences'] : '' }}
                                                </x-filament::badge>
                                                @break
                                            @case('failed')
                                                <x-filament::badge color="warning">Python-версия упала</x-filament::badge>
                                                @break
                                            @case('timeout')
                                                <x-filament::badge color="warning">не уложилась во время</x-filament::badge>
                                                @break
                                            @case('skipped')
                                                <x-filament::badge color="gray">не сверялась</x-filament::badge>
                                                @break
                                            @default
                                                <span class="text-gray-500">—</span>
                                        @endswitch

                                        @if (! empty($python['note']) || ! empty($python['problems']))
                                            <details class="mt-1 text-xs text-gray-500">
                                                <summary class="cursor-pointer">подробности</summary>
                                                @if (! empty($python['note']))
                                                    <pre class="mt-1 whitespace-pre-wrap">{{ $python['note'] }}</pre>
                                                @endif
                                                @foreach ($python['problems'] ?? [] as $problem)
                                                    <p class="mt-1">{{ $problem }}</p>
                                                @endforeach
                                            </details>
                                        @endif
                                    </td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                </div>
            </x-filament::section>

            <x-filament::section collapsible collapsed>
                <x-slot name="heading">Что значит «Сверка с Python»</x-slot>
                <div class="space-y-2 text-sm text-gray-600 dark:text-gray-300">
                    <p>
                        Площадка постепенно переезжает с PHP на Python. Пока переезд идёт, каждая выгрузка делается
                        обеими версиями на одних и тех же данных, и книги сверяются ячейка в ячейку.
                        Скачиваете вы PHP-файл — проверенный, как и раньше.
                    </p>
                    <p>
                        «Совпала» — Python-версия выгрузила ровно то же самое. Когда так будет несколько раз подряд,
                        выгрузку можно переключить на Python. «Расходится» или «упала» на выгрузку не влияют:
                        ваши файлы готовы, а расхождение — повод разобраться до переключения.
                    </p>
                </div>
            </x-filament::section>
        @endif
    </div>
</x-filament-panels::page>
