import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { I18nProvider } from '@i18n'
import { initErrorCapture } from './services/bugReport'
import './App.css'

// Activate global error capture before mounting React.
initErrorCapture()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>,
)
