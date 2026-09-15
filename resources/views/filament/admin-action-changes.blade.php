{{--
    Что изменилось в одной записи журнала.

    Две колонки «было — стало» вместо сырого JSON: журнал читает человек,
    который выясняет, кто сломал настройку, а не разбирает структуру данных.
--}}
@php
    $fields = array_keys($before + $after);
@endphp

<div class="fi-section-content overflow-x-auto">
    <table class="w-full text-sm">
        <thead>
            <tr class="border-b border-gray-200 dark:border-white/10">
                <th class="py-2 pr-4 text-start font-medium text-gray-500 dark:text-gray-400">Поле</th>
                <th class="py-2 pr-4 text-start font-medium text-gray-500 dark:text-gray-400">Было</th>
                <th class="py-2 text-start font-medium text-gray-500 dark:text-gray-400">Стало</th>
            </tr>
        </thead>
        <tbody>
            @foreach ($fields as $field)
                <tr class="border-b border-gray-100 dark:border-white/5 align-top">
                    <td class="py-2 pr-4 font-mono text-xs text-gray-700 dark:text-gray-300">{{ $field }}</td>
                    <td class="py-2 pr-4 text-gray-500 dark:text-gray-400">
                        {{ \App\Support\AdminLog::readable($before[$field] ?? null) }}
                    </td>
                    <td class="py-2 text-gray-950 dark:text-white">
                        {{ \App\Support\AdminLog::readable($after[$field] ?? null) }}
                    </td>
                </tr>
            @endforeach
        </tbody>
    </table>
</div>
