import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ToastProvider } from './components/Toast';
import Dashboard from './pages/Dashboard';
import Reader from './pages/Reader';

function App() {
  return (
    <ToastProvider>
      <Router>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/read/:id" element={<Reader />} />
        </Routes>
      </Router>
    </ToastProvider>
  );
}

export default App;
