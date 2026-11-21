import React, { lazy, Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Link, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import ResponsiveShell from './components/ResponsiveShell'
import { FeedbackProvider } from './components/Feedback'
import { Spinner } from './components/Spinner'
import ErrorBoundary, { installGlobalErrorHandlers } from './components/ErrorBoundary'
import SetupWizard from './components/SetupWizard'
import './i18n'
import './index.css'
import './styles.css'
import { t } from './lib/t'
import { bootstrapAdminToken } from './lib/queries'

// 路由级代码分割（React.lazy + Suspense）
const VisitorChat = lazy(() => import('./VisitorChat'))
const Settings = lazy(() => import('./Settings'))
const Instances = lazy(() => import('./pages/Instances'))
const Sessions = lazy(() => import('./pages/Sessions'))
const Capabilities = lazy(() => import('./pages/Capabilities'))
const Policy = lazy(() => import('./pages/Policy'))
const Observe = lazy(() => import('./pages/Observe'))
const Reminders = lazy(() => import('./Reminders'))

function NotFound() {
  return (
    <div className="p-8">
      <h2 className="text-lg font-semibold">{t('页面不存在')}</h2>
      <p className="text-sm text-muted mt-2">{t('地址可能写错了，或者功能已经改名。')}</p>
      <Link className="btn mt-4" to="/">{t('回到对话')}</Link>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <FeedbackProvider>
          <SetupWizard />
          <ResponsiveShell>
            <Suspense fallback={<Spinner full />}>
              <ErrorBoundary>
              <Routes>
                <Route path="/" element={<VisitorChat />} />
                {/* 角色三入口合并后的兼容：旧子路由回到角色工作台的对应子页 */}
                <Route path="/capabilities/persona-caps" element={<Navigate to="/capabilities?view=persona&role=caps" replace />} />
                <Route path="/capabilities/cards" element={<Navigate to="/capabilities?view=persona&role=cards" replace />} />
                <Route path="/instances" element={<Instances />} />
                <Route path="/sessions" element={<Sessions />} />
                <Route path="/capabilities/:tab" element={<Capabilities />} />
                <Route path="/capabilities" element={<Capabilities />} />
                {/* 策略页压平后的兼容：旧二级页回到对应一级 tab */}
                <Route path="/policy/rules" element={<Navigate to="/policy?view=permission" replace />} />
                <Route path="/policy/approvals" element={<Navigate to="/policy?view=approvals" replace />} />
                <Route path="/policy/permission" element={<Navigate to="/policy?view=permission" replace />} />
                <Route path="/policy/guardrail" element={<Navigate to="/policy?view=guardrail" replace />} />
                <Route path="/policy/hooks" element={<Navigate to="/policy?view=hooks" replace />} />
                <Route path="/policy/inj" element={<Navigate to="/policy?view=inj" replace />} />
                <Route path="/policy/:tab" element={<Policy />} />
                <Route path="/policy" element={<Policy />} />
                <Route path="/observe" element={<Observe />} />
                <Route path="/reminders" element={<Reminders />} />
                {/* 旧入口一版重定向：必须放在 /settings/:tab 之前，否则会被动态段吞掉 */}
                <Route path="/settings/kb" element={<Navigate to="/capabilities/kb" replace />} />
                <Route path="/settings/cards" element={<Navigate to="/capabilities?view=persona&role=cards" replace />} />
                <Route path="/settings/persona-caps" element={<Navigate to="/capabilities?view=persona&role=caps" replace />} />
                <Route path="/settings/providers" element={<Navigate to="/settings/model" replace />} />
                <Route path="/settings/local" element={<Navigate to="/settings/model?model=local" replace />} />
                <Route path="/settings/params" element={<Navigate to="/settings/model?model=params" replace />} />
                <Route path="/operator" element={<Navigate to="/sessions?view=workbench" replace />} />
                <Route path="/persona" element={<Navigate to="/capabilities?view=persona" replace />} />
                <Route path="/annotations" element={<Navigate to="/sessions?view=annotate" replace />} />
                <Route path="/settings/:tab" element={<Settings scope="settings" />} />
                <Route path="/settings" element={<Settings scope="settings" />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
              </ErrorBoundary>
            </Suspense>
          </ResponsiveShell>
        </FeedbackProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

installGlobalErrorHandlers()

// 先尝试本机令牌引导，再挂载应用。
// 顺序很重要：先渲染会让管理页在无令牌时发出一批 401 请求，
// 然后永远停在 Loading（而不是显示 TokenGate）。这一步很快（一次本地请求），
// 失败也继续渲染，不会白屏。
bootstrapAdminToken().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')).render(<App />)
})
