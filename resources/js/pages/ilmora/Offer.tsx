import { Fragment, useEffect, useState, type ReactNode } from 'react';
import { IlmoraLayout } from '@/components/ilmora/IlmoraLayout';
import { Link } from '@/components/ui/Link';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';
import { loadDraft } from './draft';
import { cleanName, formatPhone, phoneDigits, type IlmoraForm } from './rules';

/**
 * Публичная оферта с заявлением (python/savdex/ilmora/offer/<язык>.txt,
 * разметка — offer/README.md). Пустые места заявления — ФИО, ПИНФЛ или ИНН,
 * телефон, отметки и дата — заполняются из анкеты (черновик во вкладке,
 * draft.ts); на сервер отсюда ничего не уходит. «Вернуться к регистрации»
 * ведёт к той же заполненной анкете.
 */
export default function IlmoraOffer({ paragraphs = [] }: { paragraphs?: string[] }) {
    // Хранилище есть только в браузере: на сервере и в первой отрисовке — пустые места
    const [draft, setDraft] = useState<Partial<IlmoraForm>>({});
    const [now, setNow] = useState('');

    useEffect(() => {
        setDraft(loadDraft() ?? {});
        setNow(stamp(new Date()));
    }, []);

    const marks = fill(draft, now);

    return (
        <IlmoraLayout title={t('ilmora.offer.title')}>
            <article className="ilmora-card ilmora-card--doc">
                {paragraphs.length > 0 ? (
                    <div className="ilmora-doc">{paragraphs.map((text, i) => block(text, i, marks))}</div>
                ) : (
                    <>
                        <h1 className="ilmora-title">{t('ilmora.offer.title')}</h1>
                        <p className="ilmora-doc__pending">{t('ilmora.offer.pending')}</p>
                    </>
                )}
            </article>

            <Link href={routes.ilmoraRegister} className="ilmora-back">
                ← {t('ilmora.offer.back')}
            </Link>
        </IlmoraLayout>
    );
}

type Marks = Record<string, ReactNode>;

/** Чем заполнить метки: анкета, а чего нет — черта, как на бумаге */
function fill(draft: Partial<IlmoraForm>, now: string): Marks {
    const value = (text: string) =>
        text ? <span className="ilmora-doc__value">{text}</span> : <span className="ilmora-doc__blank">______________</span>;
    const kind = draft.person_type;
    const number = kind === 'individual' ? draft.pinfl : kind === 'legal' ? draft.tin : '';
    const phone = phoneDigits(draft.phone ?? '');
    const box = (on: boolean | undefined) => (
        <span className={cn('ilmora-doc__box', on && 'is-on')} aria-hidden>
            {on ? '☑' : '☐'}
        </span>
    );

    return {
        '[ФИО]': value(cleanName(draft.full_name ?? '')),
        '[НОМЕР_НАЗВАНИЕ]': t(
            kind === 'individual'
                ? 'ilmora.offer.number_pinfl'
                : kind === 'legal'
                  ? 'ilmora.offer.number_tin'
                  : 'ilmora.offer.number_any',
        ),
        '[НОМЕР]': value((number ?? '').replace(/[\s-]/g, '')),
        '[ТЕЛЕФОН]': value(phone ? `+998 ${formatPhone(phone)}` : ''),
        '[ДАТА]': value(now),
        '[ОТМЕТКА_ОФЕРТА]': box(draft.offer_read),
        '[ОТМЕТКА_ПОДПИСЬ]': box(draft.offer_sign),
    };
}

/** «15.10.2026 14:05» */
function stamp(date: Date): string {
    const two = (n: number) => String(n).padStart(2, '0');

    return `${two(date.getDate())}.${two(date.getMonth() + 1)}.${date.getFullYear()} ${two(date.getHours())}:${two(date.getMinutes())}`;
}

/** Абзац текста оферты по разметке README: заголовки, «город | редакция», строки справа */
function block(text: string, key: number, marks: Marks): ReactNode {
    if (text === '---') return <hr key={key} className="ilmora-doc__rule" />;
    if (text.startsWith('# ')) return <h2 key={key} className="ilmora-doc__title">{withMarks(text.slice(2), marks)}</h2>;
    if (text.startsWith('### ')) return <p key={key} className="ilmora-doc__subtitle">{withMarks(text.slice(4), marks)}</p>;
    if (text.startsWith('## ')) return <h3 key={key} className="ilmora-doc__section">{withMarks(text.slice(3), marks)}</h3>;
    if (text.startsWith('> ')) return <p key={key} className="ilmora-doc__right">{withMarks(text.slice(2), marks)}</p>;

    if (text.startsWith('~ ')) {
        const [left, right = ''] = text.slice(2).split(' | ');

        return (
            <p key={key} className="ilmora-doc__meta">
                <span>{left}</span>
                <span>{right}</span>
            </p>
        );
    }

    return <p key={key}>{withMarks(text, marks)}</p>;
}

const MARK = /(\[[А-ЯЁ_]+\])/;

/** Текст с метками [ФИО], [ТЕЛЕФОН]…: на месте метки — значение из анкеты */
function withMarks(text: string, marks: Marks): ReactNode {
    return text.split(MARK).map((part, i) => <Fragment key={i}>{part in marks ? marks[part] : part}</Fragment>);
}
