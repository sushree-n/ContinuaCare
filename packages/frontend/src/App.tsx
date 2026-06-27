import { Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import Demo from './pages/Demo'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/demo" element={<Demo />} />
    </Routes>
  )
}
