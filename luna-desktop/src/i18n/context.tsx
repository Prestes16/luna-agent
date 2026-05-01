import React, { createContext, useCallback } from 'react'
import { translations, Locale, TranslationKey } from './translations'
import { useStore } from '@store/appStore'

// ── Types ─────────────────────────────────────────────────────────────────────

interface I18nContextValue {
  locale: Locale
  setLocale: (l: Locale) => void
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string
}

// ── Context ───────────────────────────────────────────────────────────────────

const I18nContext = createContext<I18nContextValue>({
  locale: 'pt-BR',
  setLocale: () => {},
  t: (key) => key,
})

// ── Provider ──────────────────────────────────────────────────────────────────

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { locale, setLocale } = useStore()

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>): string => {
      const lang = (locale as Locale) in translations ? (locale as Locale) : 'pt-BR'
      const dict = translations[lang] as Record<string, string>
      let str = dict[key] ?? (translations['pt-BR'] as Record<string, string>)[key] ?? key

      // Simple {{var}} substitution
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          str = str.replace(new RegExp(`\\{\\{${k}\\}\\}`, 'g'), String(v))
        })
      }
      return str
    },
    [locale]
  )

  return (
    <I18nContext.Provider value={{ locale: locale as Locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  )
}

// ── Context re-export for hooks ───────────────────────────────────────────────
// NOTE: useI18n and useTranslation are in ./hooks.ts (separate file required
// for Vite Fast Refresh — mixing components + hooks in one file breaks HMR)
export { I18nContext }
