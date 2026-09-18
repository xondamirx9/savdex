import { useBrandLogo } from '@/lib/brand';
import { cn } from '@/lib/cn';

/**
 * Логотип.
 *
 * Словесная часть — единый элемент .logo-word. Если разбить её на текстовый
 * узел «Savd» и <span>ex</span> внутри flex-контейнера с gap, каждый станет
 * самостоятельным flex-элементом и между ними появится зазор — логотип
 * прочитается как «Savd ex». На этом уже спотыкались в прототипе.
 *
 * asContent = true, когда логотип вставляется внутрь уже существующей
 * ссылки: вложенный <a> внутри <a> недопустим.
 */
export function Logo({ inverted = false, asContent = false }: { inverted?: boolean; asContent?: boolean }) {
    const logo = useBrandLogo();

    const content = (
        <>
            <img src={logo.src} alt="" aria-hidden className={cn('logo-img', logo.custom && 'logo-img--custom')} />
            {/* translate="no": браузерные переводчики превращали
                бренд в «Сохранённый Экс» */}
            <span className="logo-word notranslate" translate="no">
                Savd<span>ex</span>
            </span>
        </>
    );

    if (asContent) return content;

    return <span className={cn('logo', inverted && 'logo--inverted')}>{content}</span>;
}
