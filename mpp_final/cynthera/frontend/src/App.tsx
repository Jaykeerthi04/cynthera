import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { MainLayout } from './layouts/MainLayout';
import { LandingPage } from './pages/LandingPage';
import { ResultPage } from './pages/ResultPage';
import { ReportPage } from './pages/ReportPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<LandingPage />} />
          <Route path="analysis/:id" element={<ResultPage />} />
          <Route path="analysis/:id/report" element={<ReportPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
