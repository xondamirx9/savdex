/**
 * Склейка классов с отсевом пустых значений.
 *
 * Намеренно без clsx и tailwind-merge: в UI-ките варианты не пересекаются
 * по свойствам, поэтому разрешать конфликты классов нечем и незачем.
 * Если понадобится переопределять цвет кнопки через className — тогда
 * добавим tailwind-merge, а пока это лишние 8 КБ в бандле.
 */
export function cn(...parts: Array<string | false | null | undefined>): string {
    return parts.filter(Boolean).join(' ');
}
