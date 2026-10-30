
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import { AuthProvider } from "./context/AuthContext";
import { useAuth } from "./context/useAuth";

import Login from "./pages/Login";
import Register from "./pages/Register";
import StudentDashboard from "./pages/StudentDashboard";
import OwnerDashboard from "./pages/OwnerDashboard";
import ResourceDetails from "./pages/ResourceDetails";
import Booking from "./pages/Booking";

function DashboardRedirect() {
    const { user, loading } = useAuth();

    if (loading) return <p>Loading...</p>;

    if (!user) return <Navigate to="/login" replace />;

    if (user.role === "OWNER") {
        return <Navigate to="/owner/dashboard" replace />;
    }

    if (user.role === "ADMIN") {
        return <Navigate to="/admin/dashboard" replace />;
    }

    return <Navigate to="/student/dashboard" replace />;
}

function ProtectedRoute({ children, allowedRoles }) {
    const { user, loading } = useAuth();

    if (loading) return <p>Loading...</p>;

    if (!user) return <Navigate to="/login" replace />;

    if (allowedRoles && !allowedRoles.includes(user.role)) {
        return <Navigate to="/" replace />;
    }

    return children;
}

function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    <Route path="/" element={<DashboardRedirect />} />

                    <Route path="/login" element={<Login />} />
                    <Route path="/register" element={<Register />} />

                    <Route
                        path="/student/dashboard"
                        element={
                            <ProtectedRoute allowedRoles={["STUDENT"]}>
                                <StudentDashboard />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/owner/dashboard"
                        element={
                            <ProtectedRoute allowedRoles={["OWNER"]}>
                                <OwnerDashboard />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/resources/:id"
                        element={
                            <ProtectedRoute allowedRoles={["STUDENT"]}>
                                <ResourceDetails />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/book/:id"
                        element={
                            <ProtectedRoute allowedRoles={["STUDENT"]}>
                                <Booking />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/admin/dashboard"
                        element={
                            <ProtectedRoute allowedRoles={["ADMIN"]}>
                                <h1>Admin Dashboard — Coming Soon</h1>
                            </ProtectedRoute>
                        }
                    />

                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
            </AuthProvider>
        </BrowserRouter>
    );
}

export default App;
