import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { BookOpen, Users, FileText, Sparkles, ArrowRight } from 'lucide-react';

export default function Landing() {
  const { login, isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();

  // Redirect authenticated users to dashboard
  React.useEffect(() => {
    if (!loading && isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [loading, isAuthenticated, navigate]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6]">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#F9F8F6]/80 backdrop-blur-md border-b border-[#E5E5E5]">
        <div className="max-w-7xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#1A1A1A] rounded-lg flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-[#1A1A1A]">ThinkificAI</span>
          </div>
          <Button 
            data-testid="login-button"
            onClick={login}
            className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-full px-6"
          >
            Sign In
          </Button>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-6 md:px-12">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-2 gap-16 items-center">
            {/* Left Column */}
            <div className="animate-fade-in">
              <p className="text-sm text-[#888] uppercase tracking-widest mb-4">
                AI-Powered Learning
              </p>
              <h1 className="text-5xl md:text-7xl font-light tracking-tight leading-[1.1] text-[#1A1A1A] mb-6">
                Your personal
                <span className="block mt-2">
                  <span className="bg-[#FDE047] px-2">AI tutor</span>
                </span>
              </h1>
              <p className="text-lg md:text-xl text-[#5A5A5A] leading-relaxed max-w-lg mb-8">
                Transform your cohort learning experience with AI-powered homework reviews. 
                Upload workbooks, case studies, and assignments—let AI provide encouraging, 
                personalized feedback.
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <Button 
                  data-testid="get-started-btn"
                  onClick={login}
                  className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg px-8 py-6 text-lg font-medium group"
                >
                  Get Started
                  <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
                </Button>
                <Button 
                  variant="outline"
                  className="border-[#1A1A1A] text-[#1A1A1A] hover:bg-[#F2F0ED] rounded-lg px-8 py-6 text-lg"
                >
                  Learn More
                </Button>
              </div>
            </div>

            {/* Right Column - Image */}
            <div className="relative animate-slide-in" style={{ animationDelay: '0.2s' }}>
              <div className="aspect-[4/3] rounded-2xl overflow-hidden shadow-[0_12px_24px_rgba(0,0,0,0.06)]">
                <img 
                  src="https://images.unsplash.com/photo-1758270705317-3ef6142d306f?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2Nzh8MHwxfHNlYXJjaHw0fHx1bml2ZXJzaXR5JTIwc3R1ZGVudHMlMjBzdHVkeWluZyUyMGdyb3VwfGVufDB8fHx8MTc3MzgyOTE1NXww&ixlib=rb-4.1.0&q=85"
                  alt="Students studying together"
                  className="w-full h-full object-cover"
                />
              </div>
              {/* Floating card */}
              <div className="absolute -bottom-6 -left-6 bg-white rounded-xl p-4 shadow-lg border border-[#E5E5E5] animate-fade-in" style={{ animationDelay: '0.4s' }}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-[#D1FAE5] rounded-full flex items-center justify-center">
                    <Sparkles className="w-5 h-5 text-[#065F46]" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#1A1A1A]">AI Feedback</p>
                    <p className="text-xs text-[#888]">Encouraging & insightful</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-6 md:px-12 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-sm text-[#888] uppercase tracking-widest mb-4">Features</p>
            <h2 className="text-3xl md:text-5xl font-light tracking-tight text-[#1A1A1A]">
              Everything you need for
              <span className="block">cohort learning</span>
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-8 stagger-children">
            {/* Feature 1 */}
            <div className="bg-[#F9F8F6] rounded-xl p-8 hover:-translate-y-1 transition-transform duration-300">
              <div className="w-12 h-12 bg-[#E0F2FE] rounded-xl flex items-center justify-center mb-6">
                <FileText className="w-6 h-6 text-[#075985]" />
              </div>
              <h3 className="text-xl font-normal text-[#1A1A1A] mb-3">Weekly Workbooks</h3>
              <p className="text-[#5A5A5A] leading-relaxed">
                Upload and organize course materials by week. Support for PDF and Word documents.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="bg-[#F9F8F6] rounded-xl p-8 hover:-translate-y-1 transition-transform duration-300">
              <div className="w-12 h-12 bg-[#FDE047] rounded-xl flex items-center justify-center mb-6">
                <Users className="w-6 h-6 text-[#1A1A1A]" />
              </div>
              <h3 className="text-xl font-normal text-[#1A1A1A] mb-3">Cohort Management</h3>
              <p className="text-[#5A5A5A] leading-relaxed">
                Create cohorts, add students, and manage your learning groups with ease.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="bg-[#F9F8F6] rounded-xl p-8 hover:-translate-y-1 transition-transform duration-300">
              <div className="w-12 h-12 bg-[#D1FAE5] rounded-xl flex items-center justify-center mb-6">
                <Sparkles className="w-6 h-6 text-[#065F46]" />
              </div>
              <h3 className="text-xl font-normal text-[#1A1A1A] mb-3">AI Reviews</h3>
              <p className="text-[#5A5A5A] leading-relaxed">
                Get encouraging, personalized feedback on student submissions powered by GPT-5.2.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-6 md:px-12">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl md:text-5xl font-light tracking-tight text-[#1A1A1A] mb-6">
            Ready to transform your
            <span className="block">teaching experience?</span>
          </h2>
          <p className="text-lg text-[#5A5A5A] mb-8 max-w-2xl mx-auto">
            Join instructors who are using AI to provide better, faster feedback to their students.
          </p>
          <Button 
            data-testid="cta-sign-up"
            onClick={login}
            className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-full px-10 py-6 text-lg font-medium"
          >
            Start Free Today
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 md:px-12 border-t border-[#E5E5E5]">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-[#1A1A1A] rounded flex items-center justify-center">
              <BookOpen className="w-3 h-3 text-white" />
            </div>
            <span className="text-sm text-[#888]">ThinkificAI Tutor</span>
          </div>
          <p className="text-sm text-[#888]">© 2024 All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
