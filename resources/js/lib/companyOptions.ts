/**
 * Списки полей компании — общие для страницы «Компания» и блока
 * «Данные компании» в настройках профиля.
 */
export const EMPLOYEE_RANGES = ['1-10', '10-50', '50-100', '100-500', '500+'];

/**
 * Как справочник company_types (Company::FALLBACK_TYPES). «retailer» — для
 * компаний, заведённых до справочника: их тип не должен читаться «не указан».
 */
export const COMPANY_TYPES = ['manufacturer', 'importer', 'distributor', 'trader', 'service', 'retailer'];

/**
 * Заполнено ли поле: Company::profileValue на сервере.
 *
 * Заполненное меняется раз в полгода и только в настройках, пустое
 * можно заполнить когда угодно.
 */
export function isFilled(value: unknown): boolean {
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === 'boolean') return value;
    if (value === null || value === undefined) return false;

    return String(value).trim() !== '';
}
