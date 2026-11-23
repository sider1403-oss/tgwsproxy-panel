import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Connections from './pages/Connections'
import Keys from './pages/Keys'
import Logs from './pages/Logs'
import Service from './pages/Service'
import Config from './pages/Config'
import Diagnostics from './pages/Diagnostics'
import Alerts from './pages/Alerts'
import Security from './pages/Security'
import Login from './pages/Login'
import Setup from './pages/Setup'
import { useAuth } from './lib/auth'
import { Spinner } from './components/ui'

export default function App() {
  const { loading, user, setupRequired } = useAuth()

  if (loading) {
    return (
      <div className="auth-bg flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-muted">
          <Spinner /> Проверка сессии…
        </div>
      </div>
    )
  }

  if (setupRequired) return <Setup />
  if (!user) return <Login />
  if (user.must_change_password) return <Security forced />

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/connections" element={<Connections />} />
        <Route path="/keys" element={<Keys />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/service" element={<Service />} />
        <Route path="/diagnostics" element={<Diagnostics />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/security" element={<Security />} />
        <Route path="/config" element={<Config />} />
        <Route path="*" element={<Dashboard />} />
      </Route>
    </Routes>
  )
}
