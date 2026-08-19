import { BrowserRouter, Routes, Route, useLocation, Navigate, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrandingProvider } from "./context/BrandingContext";
import { Toaster } from "./components/ui/sonner";

// Pages
import Landing from "./pages/Landing";
import AuthCallback from "./pages/AuthCallback";
import RoleSelection from "./pages/RoleSelection";
import InstructorDashboard from "./pages/InstructorDashboard";
import CohortDetail from "./pages/CohortDetail";
import Submissions from "./pages/Submissions";
import VenturePath from "./pages/VenturePath";
import SubmissionDetail from "./pages/SubmissionDetail";
import ProgressTracking from "./pages/ProgressTracking";
import MaterialLibrary from "./pages/MaterialLibrary";
import ThinkificSync from "./pages/ThinkificSync";
import AdminManagement from "./pages/AdminManagement";
import BrandingSettings from "./pages/BrandingSettings";
import VenturePathAdmin from "./pages/VenturePathAdmin";
import InvitePage from "./pages/InvitePage";
import DirectSubmit, { DirectSubmitStable, AssignmentMilestoneSubmit } from "./pages/DirectSubmit";
import StudentAssignmentsDashboard from "./pages/StudentAssignmentsDashboard";
import CoachMaxPage from "./pages/CoachMaxPage";
import CoachMaxInsightsPage from "./pages/CoachMaxInsightsPage";
import RubricLibrary from "./pages/RubricLibrary";
import AssignmentTemplatesPage from "./pages/AssignmentTemplatesPage";
import AdminSupportTicketsPage from "./pages/AdminSupportTicketsPage";
import SupportWidget from "./components/SupportWidget";

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
    // Save intended destination so AuthCallback can redirect back after login
    const intended = location.pathname + location.search;
    if (intended !== '/' && intended !== '/dashboard') {
      localStorage.setItem('redirect_after_login', intended);
    }
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  return children;
};

// Dashboard router - redirects based on role
const DashboardRouter = () => {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && user && !user.role) {
      // User has no role selected, redirect to role selection
      navigate('/role-selection', { replace: true });
    }
  }, [loading, user, navigate]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  // If no role, show loading (will redirect via useEffect)
  if (!user?.role) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (user?.role === 'instructor' || user?.role === 'super_admin') {
    return <InstructorDashboard />;
  }

  return <StudentAssignmentsDashboard />;
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
      <Route path="/progress" element={
        <ProtectedRoute>
          <ProgressTracking />
        </ProtectedRoute>
      } />
      <Route path="/venture-path" element={
        <ProtectedRoute>
          <VenturePath />
        </ProtectedRoute>
      } />
      <Route path="/venture-path/student/:studentId" element={
        <ProtectedRoute>
          <VenturePath />
        </ProtectedRoute>
      } />
      <Route path="/library" element={
        <ProtectedRoute>
          <MaterialLibrary />
        </ProtectedRoute>
      } />
      <Route path="/rubrics" element={
        <ProtectedRoute>
          <RubricLibrary />
        </ProtectedRoute>
      } />
      <Route path="/assignment-templates" element={
        <ProtectedRoute>
          <AssignmentTemplatesPage />
        </ProtectedRoute>
      } />
      <Route path="/thinkific" element={
        <ProtectedRoute>
          <ThinkificSync />
        </ProtectedRoute>
      } />
      <Route path="/admin" element={
        <ProtectedRoute>
          <AdminManagement />
        </ProtectedRoute>
      } />
      <Route path="/admin/branding" element={
        <ProtectedRoute>
          <BrandingSettings />
        </ProtectedRoute>
      } />
      <Route path="/admin/venture-path" element={
        <ProtectedRoute>
          <VenturePathAdmin />
        </ProtectedRoute>
      } />
      <Route path="/invite/:code" element={<InvitePage />} />
      <Route path="/submit/:materialId" element={<DirectSubmit />} />
      <Route path="/submit/w/:week/:submissionType" element={<DirectSubmitStable />} />
      <Route path="/submit/a/:assignmentId/w/:week" element={<AssignmentMilestoneSubmit />} />
      <Route path="/coach-max/:submissionId" element={
        <ProtectedRoute>
          <CoachMaxPage />
        </ProtectedRoute>
      } />
      <Route path="/coach-max-insights/:cohortId" element={
        <ProtectedRoute>
          <CoachMaxInsightsPage />
        </ProtectedRoute>
      } />
      <Route path="/admin/support-tickets" element={
        <ProtectedRoute>
          <AdminSupportTicketsPage />
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
      <BrandingProvider>
        <AuthProvider>
          <AppRouter />
          <SupportWidget />
          <Toaster position="top-right" richColors />
        </AuthProvider>
      </BrandingProvider>
    </BrowserRouter>
  );
}

export default App;
