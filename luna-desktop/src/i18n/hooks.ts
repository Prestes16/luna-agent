/**
 * i18n hooks — kept in a SEPARATE file from context.tsx on purpose.
 *
 * Vite Fast Refresh requires that each file exports ONLY React components
 * OR ONLY hooks/utilities — never a mix of both.
 * context.tsx exports I18nProvider (a component), so hooks live here.
 */
import { useContext } from 'react'
import { I18nContext } from './context'

export const useI18n = () => useContext(I18nContext)

/** Alias — lets components do: import { useTranslation } from '@i18n/hooks' */
export const useTranslation = useI18n
