import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Reader from './pages/Reader';

function App() {
  return (
    <Router>
      <Routes>
        {/* 默认跳转到仪表盘 */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        
        {/* 仪表盘/首页 */}
        <Route path="/dashboard" element={<Dashboard />} />
        
        {/* 阅读器页面，:id 代表论文ID */}
        <Route path="/read/:id" element={<Reader />} />
      </Routes>
    </Router>
  );
}

export default App;