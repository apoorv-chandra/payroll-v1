import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { I18nProvider } from "./contexts/I18nContext";
import Login, { FullScreenLoader, homeFor, postLoginPath } from "./pages/Login";
import Signup from "./pages/Signup";
import AdminApp from "./pages/AdminApp";
import EmployerApp from "./pages/EmployerApp";
import EmployeeApp from "./pages/EmployeeApp";
import Launchpad from "./pages/Launchpad";
import StudentsApp from "./pages/StudentsApp";

function Protected({ allow, children }) {
  const { user } = useAuth();
  if (user === undefined) return <FullScreenLoader />;
  if (!user) return <Navigate to="/login" replace />;
  if (allow && !allow.includes(user.role)) return <Navigate to={homeFor(user)} replace />;
  return children;
}

function HomeRedirect() {
  const { user } = useAuth();
  if (user === undefined) return <FullScreenLoader />;
  // No feature list yet here — postLoginPath falls back to role-based home,
  // which is fine because the eventual target route refetches features.
  return <Navigate to={user ? postLoginPath(user, null) : "/login"} replace />;
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<HomeRedirect />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/admin/*" element={<Protected allow={["super_admin"]}><AdminApp /></Protected>} />
            <Route path="/employer/*" element={<Protected allow={["employer"]}><EmployerApp /></Protected>} />
            <Route path="/me/*" element={<Protected allow={["employee"]}><EmployeeApp /></Protected>} />
            <Route path="/launchpad" element={<Protected><Launchpad /></Protected>} />
            <Route path="/school/*" element={<Protected><StudentsApp /></Protected>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  );
}
