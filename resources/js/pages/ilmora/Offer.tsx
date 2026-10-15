import { IlmoraLayout } from '@/components/ilmora/IlmoraLayout';
import { Link } from '@/components/ui/Link';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Публичная оферта ILMORA. Текст — python/savdex/ilmora/offer/<язык>.txt;
 * пока его нет — «Текст оферты будет опубликован позже».
 */
export default function IlmoraOffer({ paragraphs = [] }: { paragraphs?: string[] }) {
    return (
        <IlmoraLayout title={t('ilmora.offer.title')}>
            <article className="ilmora-card">
                <h1 className="ilmora-title">{t('ilmora.offer.title')}</h1>

                <div className="ilmora-offer">
                    {paragraphs.length > 0 ? (
                        paragraphs.map((text, i) => <p key={i}>{text}</p>)
                    ) : (
                        <p className="ilmora-offer__pending">{t('ilmora.offer.pending')}</p>
                    )}
                </div>
            </article>

            <Link href={routes.ilmoraRegister} className="ilmora-back">
                ← {t('ilmora.offer.back')}
            </Link>
        </IlmoraLayout>
    );
}
