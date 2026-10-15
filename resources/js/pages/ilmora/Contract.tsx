import { Fragment, useEffect, useState, type ReactNode } from 'react';
import { IlmoraLayout } from '@/components/ilmora/IlmoraLayout';
import { Link } from '@/components/ui/Link';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';
import { draftName } from './draft';

/** Метка ФИО в тексте договора (python/savdex/ilmora/contract/<язык>.txt) */
const NAME_MARK = '[ФИО]';

/**
 * Договор ILMORA. Первая строка — «Я, <ФИО>, …»: ФИО берётся из анкеты
 * (черновик во вкладке, draft.ts), на сервер не уходит. Тем же ФИО
 * заменяется [ФИО] в самом тексте. Текст — contract/<язык>.txt; пока его
 * нет — «Полный текст договора будет опубликован позже». «Вернуться к
 * регистрации» ведёт к той же заполненной анкете.
 */
export default function IlmoraContract({ paragraphs = [] }: { paragraphs?: string[] }) {
    // Хранилище есть только в браузере: на сервере и в первой отрисовке — без имени
    const [name, setName] = useState('');

    useEffect(() => setName(draftName()), []);

    const person = (
        <span className={cn('ilmora-contract__name', !name && 'ilmora-contract__name--missing')}>
            {name || t('ilmora.contract.name_missing')}
        </span>
    );

    return (
        <IlmoraLayout title={t('ilmora.contract.title')}>
            <article className="ilmora-card">
                <h1 className="ilmora-title">{t('ilmora.contract.title')}</h1>

                <div className="ilmora-contract">
                    <p>{withName(t('ilmora.contract.preamble'), ':name', person)}</p>

                    {paragraphs.length > 0 ? (
                        paragraphs.map((text, i) => <p key={i}>{withName(text, NAME_MARK, person)}</p>)
                    ) : (
                        <p className="ilmora-contract__pending">{t('ilmora.contract.pending')}</p>
                    )}
                </div>
            </article>

            <Link href={routes.ilmoraRegister} className="ilmora-back">
                ← {t('ilmora.contract.back')}
            </Link>
        </IlmoraLayout>
    );
}

/** Текст с меткой — куски строки, на месте метки — ФИО */
function withName(text: string, mark: string, person: ReactNode): ReactNode {
    const parts = text.split(mark);

    return parts.map((part, i) => (
        <Fragment key={i}>
            {i > 0 && person}
            {part}
        </Fragment>
    ));
}
