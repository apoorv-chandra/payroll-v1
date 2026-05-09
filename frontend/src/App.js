import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import Login, { FullScreenLoader, homeFor } from "./pages/Login";
import AdminApp from "./pages/AdminApp";
import EmployerApp from "./pages/EmployerApp";
import EmployeeApp from "./pages/EmployeeApp";

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
  return <Navigate to={user ? homeFor(user) : "/login"} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/admin/*" element={<Protected allow={["super_admin"]}><AdminApp /></Protected>} />
          <Route path="/employer/*" element={<Protected allow={["employer"]}><EmployerApp /></Protected>} />
          <Route path="/me/*" element={<Protected allow={["employee"]}><EmployeeApp /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
