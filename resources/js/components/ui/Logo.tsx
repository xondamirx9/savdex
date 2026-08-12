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
    const content = (
        <>
            <img src="/images/logo-mark.svg" alt="" aria-hidden className="logo-img" />
            <span className="logo-word">
                Savd<span>ex</span>
            </span>
        </>
    );

    if (asContent) return content;

    return <span className={cn('logo', inverted && 'logo--inverted')}>{content}</span>;
}
