import { BrowserRouter, Route, Routes } from 'react-router-dom';

import Home from './pages/Home';
import EntityPage from './pages/EntityPage';

/**
 * Định tuyến của ứng dụng.
 *
 * @returns Element React.
 */
export default function App(): JSX.Element {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/entity/:entityId" element={<EntityPage />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </BrowserRouter>
  );
}
