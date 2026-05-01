/**
 * @i18n barrel — re-exports all public i18n APIs.
 * Components can import from '@i18n' without knowing the internal file structure.
 *
 * NOTE: Do NOT mix component exports and hook exports in this barrel file.
 * Keep this file as a pure re-export hub (no JSX, no component definitions).
 */
export { I18nProvider } from './context'
export { useI18n, useTranslation } from './hooks'
export type { Locale, TranslationKey } from './translations'

// Re-export hook aliases so components can import from '@i18n' directly
export { useI18n as useI18nHook } from './hooks'
