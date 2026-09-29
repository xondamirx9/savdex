import { router } from '@inertiajs/react';
import { Calculator, Code2, FileCheck2, Truck, UserSearch, Users, type LucideIcon } from 'lucide-react';
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

/**
 * Страницы направлений «Доп. услуг» — подменю в шапке.
 *
 * Тот же перечень и порядок, что ItTask::serviceMenu() на сервере:
 * там он строит список «Другие направления», здесь — подменю.
 *
 * «Подбор персонала» (recruitment) в меню не значится: рядом
 * с «HR-услугами» он читался вторым HR-пунктом, хотя это вид внутри
 * них. Страница осталась и открывается ссылкой со страницы HR-услуг,
 * поэтому в SERVICE_PAGE_ICONS и SERVICE_PAGE_BY_CODE она есть.
 */
export const SERVICE_PAGES = ['it', 'hr', 'logistics', 'customs', 'accounting'] as const;

export const SERVICE_PAGE_ICONS: Record<string, LucideIcon> = {
    it: Code2,
    hr: Users,
    recruitment: UserSearch,
    logistics: Truck,
    customs: FileCheck2,
    accounting: Calculator,
};

/** Страница направления по коду из ленты задач: hr_services → hr, hr → recruitment. */
export const SERVICE_PAGE_BY_CODE: Record<string, string> = {
    it: 'it',
    hr_services: 'hr',
    hr: 'recruitment',
    logistics: 'logistics',
    customs: 'customs',
    accounting: 'accounting',
};

export function servicePages(): { slug: string; label: string; href: string; Icon: LucideIcon }[] {
    return SERVICE_PAGES.map((slug) => ({
        slug,
        label: t(`service_pages.${slug}.title`),
        href: routes.serviceSection(slug),
        Icon: SERVICE_PAGE_ICONS[slug],
    }));
}
