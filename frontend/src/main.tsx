import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { Toaster } from 'sonner'
import { App } from './app/App'
import { WorkspaceProvider } from './app/WorkspaceContext'
import './index.css'

function normalizeLegacyRoute() {
  const hash = location.hash.replace(/^#/, '')
  if (!hash) { location.hash = '/overview'; return }
  if (hash.startsWith('/')) return
  let next = hash
  if (hash === 'dashboard' || hash === 'queue') next = 'workbench'
  else if (hash === 'reports') next = 'results'
  else if (hash === 'analysis') next = 'validation/tools'
  else if (hash.startsWith('task/')) next = `tasks/${hash.slice(5)}/review`
  else if (hash.startsWith('library/person')) next = 'library/people'
  else if (hash.startsWith('library/text')) next = 'library/terms'
  else if (hash.startsWith('library/content')) next = 'library/content'
  location.hash = `/${next}`
}
normalizeLegacyRoute()

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><HashRouter><WorkspaceProvider><App/><Toaster richColors closeButton position="bottom-right" visibleToasts={1} duration={2200} /></WorkspaceProvider></HashRouter></React.StrictMode>)
