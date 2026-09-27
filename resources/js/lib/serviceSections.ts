import { router } from '@inertiajs/react';
import type { FilterOption } from '@/components/BoardFilter';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

export interface ServiceSection {
    code: string;
    label: string;
    children: { code: string; label: string }[];
}

/** Пункт «Резюме» в HR-услугах — это не вид задачи, а отдельная страница. */
export const RESUMES_OPTION = 'resumes';

const HR_SECTION = 'hr_services';

/**
 * Пункты панели «Направление» раздела «Доп. услуги».
 *
 * Общие для ленты задач и страницы резюме: резюме стоит внутри
 * HR-услуг, и панель слева на обеих страницах должна быть одной.
 */
export function serviceFilterOptions(types: ServiceSection[]): FilterOption[] {
    return [
        { id: '', label: t('it_tasks.all_types') },
        ...types.map((type) => ({
            id: type.code,
            label: type.label,
            children: [
                ...type.children.map((child) => ({ id: child.code, label: child.label })),
                ...(type.code === HR_SECTION ? [{ id: RESUMES_OPTION, label: t('nav.resumes') }] : []),
            ],
        })),
    ];
}

/** Переход с пункта «Резюме» — на его страницу, с остальных — в ленту задач. */
export function openServiceSection(id: string, applyTaskType: (type: string) => void): void {
    if (id === RESUMES_OPTION) {
        router.get(routes.resumes);

        return;
    }

    applyTaskType(id);
}
