import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Connections from './pages/Connections'
import Clients from './pages/Clients'
import ClientDetail from './pages/ClientDetail'
import Metrics from './pages/Metrics'
import Traffic from './pages/Traffic'
import Dc from './pages/Dc'
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
        <Route path="/clients" element={<Clients />} />
        <Route path="/clients/:ip" element={<ClientDetail />} />
        <Route path="/metrics/:kind" element={<Metrics />} />
        <Route path="/traffic" element={<Traffic />} />
        <Route path="/dc" element={<Dc />} />
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
