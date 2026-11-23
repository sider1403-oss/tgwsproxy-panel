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

export default function App() {
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
        <Route path="/config" element={<Config />} />
        <Route path="*" element={<Dashboard />} />
      </Route>
    </Routes>
  )
}
