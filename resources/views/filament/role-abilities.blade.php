{{--
    Что доступно сотруднику, по разделам.

    Отдельно «от роли» и «лично»: человек, который разбирается, почему
    сотрудник это видит, ищет именно исключения, а не полный список.
--}}
<div class="fi-section-content space-y-3">
    @if ($user->isSuperadmin())
        <p class="text-sm text-gray-500 dark:text-gray-400">
            Суперадмину доступно всё, включая разделы, которых ещё не существует.
        </p>
    @elseif (empty($rows))
        <p class="text-sm text-gray-500 dark:text-gray-400">
            Прав нет: роль не назначена или все права отозваны лично.
        </p>
    @else
        <div class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="border-b border-gray-200 dark:border-white/10">
                        <th class="py-2 pr-4 text-start font-medium text-gray-500 dark:text-gray-400">Раздел</th>
                        <th class="py-2 pr-4 text-start font-medium text-gray-500 dark:text-gray-400">От роли</th>
                        <th class="py-2 text-start font-medium text-gray-500 dark:text-gray-400">Выдано лично</th>
                    </tr>
                </thead>
                <tbody>
                    @foreach ($rows as $section => $groups)
                        <tr class="border-b border-gray-100 dark:border-white/5 align-top">
                            <td class="py-2 pr-4 font-medium text-gray-950 dark:text-white">{{ $section }}</td>
                            <td class="py-2 pr-4 text-gray-600 dark:text-gray-300">
                                {{ implode(', ', $groups['от роли'] ?? []) ?: '—' }}
                            </td>
                            <td class="py-2 text-primary-600 dark:text-primary-400">
                                {{ implode(', ', $groups['лично'] ?? []) ?: '—' }}
                            </td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        </div>
    @endif
</div>
