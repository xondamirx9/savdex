import { Link } from '@/components/ui/Link';
import { Hammer } from 'lucide-react';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';
import { t } from '@/lib/i18n';

/**
 * Раздел кабинета, который ещё не сделан.
 *
 * Пустая страница читается как поломка, поэтому говорим прямо: раздел
 * в работе и когда будет. Это честнее имитации интерфейса с выдуманными
 * данными — такую на демонстрации принимают за готовую.
 */
export default function Soon({ section, sprint }: { section: string; sprint: number }) {
    return (
        <CabinetLayout title={section} heading={section}>
            <div className="bg-surface border-line rounded-card border px-6 py-14 text-center">
                <div className="ico-box ico-box-xl mx-auto mb-5">
                    <Hammer aria-hidden className="size-7" />
                </div>
                <p className="text-[17px] font-semibold">{t('cabinet.soon.title')}</p>
                <p className="text-muted mx-auto mt-2 max-w-[440px] text-[15px] leading-relaxed">
                    {t('cabinet.soon.text', { section, sprint })}{' '}
                    <span className="whitespace-nowrap">docs/SPRINTS.md</span>.
                </p>
                <Link href={routes.cabinet} className="btn btn-secondary mt-6">
                    {t('cabinet.soon.back')}
                </Link>
            </div>
        </CabinetLayout>
    );
}
