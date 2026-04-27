import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { CoachMaxInsightsTab } from '../components/cohort/CoachMaxInsightsTab';
import { ArrowLeft, MessageCircle } from 'lucide-react';

const CoachMaxInsightsPage = () => {
  const { cohortId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  if (!user || (user.role !== 'instructor' && user.role !== 'super_admin')) {
    return (
      <div className="min-h-screen bg-[#EDF5FA] flex items-center justify-center">
        <p className="text-[#666666]">Instructor access required.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#EDF5FA]">
      <header className="bg-white border-b border-[#D0E6F9] sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)} data-testid="back-btn">
            <ArrowLeft className="w-5 h-5 text-[#22438E]" />
          </Button>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#22438E] rounded-full flex items-center justify-center">
              <MessageCircle className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-[#000000]">Coach Max Insights</h1>
              <p className="text-xs text-[#666666]">Student question analysis & themes</p>
            </div>
          </div>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-8">
        <CoachMaxInsightsTab cohortId={cohortId} />
      </main>
    </div>
  );
};

export default CoachMaxInsightsPage;
