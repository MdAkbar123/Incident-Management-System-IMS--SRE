import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import LiveFeed from './pages/LiveFeed'
import IncidentDetail from './pages/IncidentDetail'
import RCAForm from './pages/RCAForm'

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/"                      element={<LiveFeed />} />
        <Route path="/incidents/:id"         element={<IncidentDetail />} />
        <Route path="/incidents/:id/rca"     element={<RCAForm />} />
      </Routes>
    </BrowserRouter>
  )
}
