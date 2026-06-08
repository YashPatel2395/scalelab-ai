import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import BenchmarkDetail from './pages/BenchmarkDetail'
import ResearchMode from './pages/ResearchMode'
import CustomWorkloads from './pages/CustomWorkloads'
import BenchmarkPacks from './pages/BenchmarkPacks'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/benchmark/:id" element={<BenchmarkDetail />} />
        <Route path="/research" element={<ResearchMode />} />
        <Route path="/custom-workloads" element={<CustomWorkloads />} />
        <Route path="/benchmark-packs" element={<BenchmarkPacks />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
