import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Toaster } from "./components/ui/sonner";

// Pages
import Landing from "./pages/Landing";
import AuthCallback from "./pages/AuthCallback";
import RoleSelection from "./pages/RoleSelection";
import InstructorDashboard from "./pages/InstructorDashboard";
import StudentDashboard from "./pages/StudentDashboard";
import CohortDetail from "./pages/CohortDetail";
import Submissions from "./pages/Submissions";
import SubmissionDetail from "./pages/SubmissionDetail";

// Protected Route component
const ProtectedRoute = ({ children }) => {
  const { user, loading, isAuthenticated } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  return children;
};

// Dashboard router - redirects based on role
const DashboardRouter = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  // New user without role selection
  if (!user?.role || user.role === 'student') {
    // Check if role needs to be selected (first time)
    // For simplicity, students go to student dashboard, instructors to instructor dashboard
  }

  if (user?.role === 'instructor') {
    return <InstructorDashboard />;
  }

  return <StudentDashboard />;
};

// App Router with session_id detection
const AppRouter = () => {
  const location = useLocation();
  
  // Detect session_id in hash DURING RENDER (not in useEffect)
  // This prevents race conditions with auth checks
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }

  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/role-selection" element={
        <ProtectedRoute>
          <RoleSelection />
        </ProtectedRoute>
      } />
      <Route path="/dashboard" element={
        <ProtectedRoute>
          <DashboardRouter />
        </ProtectedRoute>
      } />
      <Route path="/cohort/:cohortId" element={
        <ProtectedRoute>
          <CohortDetail />
        </ProtectedRoute>
      } />
      <Route path="/submissions" element={
        <ProtectedRoute>
          <Submissions />
        </ProtectedRoute>
      } />
      <Route path="/my-submissions" element={
        <ProtectedRoute>
          <Submissions />
        </ProtectedRoute>
      } />
      <Route path="/submission/:submissionId" element={
        <ProtectedRoute>
          <SubmissionDetail />
        </ProtectedRoute>
      } />
      {/* Catch-all redirect */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRouter />
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
