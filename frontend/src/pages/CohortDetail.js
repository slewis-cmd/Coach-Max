import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { 
  BookOpen, Users, FileText, ArrowLeft, Upload, UserPlus, FileUp, QrCode, UserCog, MessageCircle
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

import { MaterialsTab } from '../components/cohort/MaterialsTab';
import { StudentsTab } from '../components/cohort/StudentsTab';
import FeedbackTab from '../components/cohort/FeedbackTab';
import { CoachMaxInsightsTab } from '../components/cohort/CoachMaxInsightsTab';
import {
  AddStudentDialog, UploadMaterialDialog, SubmitHomeworkDialog,
  BulkImportDialog, InviteLinkDialog, AssignInstructorDialog, SubmitOnBehalfDialog
} from '../components/cohort/CohortDialogs';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function CohortDetail() {
  const { cohortId } = useParams();
  const navigate = useNavigate();
  const { user, isInstructor, loading: authLoading } = useAuth();
  const isSuperAdmin = user?.role === 'super_admin';
  
  const [cohort, setCohort] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [cohortSubmissions, setCohortSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Dialogs
  const [showAddStudent, setShowAddStudent] = useState(false);
  const [showUploadMaterial, setShowUploadMaterial] = useState(false);
  const [showSubmitHomework, setShowSubmitHomework] = useState(false);
  const [showBulkImport, setShowBulkImport] = useState(false);
  const [showInviteLink, setShowInviteLink] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showAssignInstructor, setShowAssignInstructor] = useState(false);
  const [showSubmitOnBehalf, setShowSubmitOnBehalf] = useState(false);
  const [submittingOnBehalf, setSubmittingOnBehalf] = useState(false);
  const [instructorsList, setInstructorsList] = useState([]);
  const [assigningInstructor, setAssigningInstructor] = useState(false);
  
  // Form states
  const [studentEmail, setStudentEmail] = useState('');
  const [studentName, setStudentName] = useState('');
  const [addingStudent, setAddingStudent] = useState(false);
  const [invitingAll, setInvitingAll] = useState(false);
  
  const [materialForm, setMaterialForm] = useState({
    title: '', description: '', week_number: 1, material_type: 'workbook', file: null, due_date: '', feedback_template: '', submission_type: '', questionnaire_fields: []
  });
  const [uploadingMaterial, setUploadingMaterial] = useState(false);
  
  const [selectedHomework, setSelectedHomework] = useState(null);
  const [homeworkFile, setHomeworkFile] = useState(null);
  const [submittingHomework, setSubmittingHomework] = useState(false);
  
  // Bulk import states
  const [bulkFile, setBulkFile] = useState(null);
  const [importingBulk, setImportingBulk] = useState(false);
  const [importResults, setImportResults] = useState(null);

  const fetchCohort = useCallback(async () => {
    try {
      const requests = [
        axios.get(`${API_URL}/api/cohorts/${cohortId}`),
        axios.get(`${API_URL}/api/cohorts/${cohortId}/materials`)
      ];
      if (isInstructor) {
        requests.push(
          axios.get(`${API_URL}/api/cohorts/${cohortId}/submissions`).catch(() => ({ data: [] }))
        );
      }
      const results = await Promise.all(requests);
      setCohort(results[0].data);
      setMaterials(results[1].data);
      if (results[2]) setCohortSubmissions(results[2].data);
    } catch (error) {
      toast.error('Failed to load cohort');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [cohortId, navigate, isInstructor]);

  useEffect(() => {
    if (!authLoading && user) fetchCohort();
  }, [authLoading, user, fetchCohort]);

  useEffect(() => {
    if (isSuperAdmin && showAssignInstructor) {
      axios.get(`${API_URL}/api/instructors`).then(res => {
        setInstructorsList(res.data);
      }).catch(() => toast.error('Failed to load instructors'));
    }
  }, [isSuperAdmin, showAssignInstructor]);

  // --- Handlers ---
  const handleAssignInstructor = async (instructorId) => {
    const isCurrentlyAssigned = cohort?.instructor_ids?.includes(instructorId);
    setAssigningInstructor(true);
    try {
      const res = await axios.post(`${API_URL}/api/cohorts/${cohortId}/assign-instructor`, {
        instructor_id: instructorId, action: isCurrentlyAssigned ? 'remove' : 'add'
      });
      toast.success(res.data.message);
      fetchCohort();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update instructor');
    } finally {
      setAssigningInstructor(false);
    }
  };

  const handleAddStudent = async () => {
    if (!studentEmail.trim()) { toast.error('Please enter student email'); return; }
    setAddingStudent(true);
    try {
      const res = await axios.post(`${API_URL}/api/cohorts/${cohortId}/students`, { email: studentEmail, name: studentName });
      toast.success(res.data.invitation_sent ? `${res.data.student.name} added — invitation email sent!` : `${res.data.student.name} added to cohort`);
      setShowAddStudent(false);
      setStudentEmail('');
      setStudentName('');
      fetchCohort();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add student');
    } finally {
      setAddingStudent(false);
    }
  };

  const handleInviteAll = async () => {
    setInvitingAll(true);
    try {
      const res = await axios.post(`${API_URL}/api/cohorts/${cohortId}/students/invite-all`, {});
      toast.success(res.data.message);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to send invitations');
    } finally {
      setInvitingAll(false);
    }
  };

  const handleRemoveStudent = async (studentId, name) => {
    if (!window.confirm(`Remove ${name} from this cohort?`)) return;
    try {
      await axios.delete(`${API_URL}/api/cohorts/${cohortId}/students/${studentId}`);
      toast.success('Student removed');
      fetchCohort();
    } catch (error) {
      toast.error('Failed to remove student');
    }
  };

  const handleToggleWeek = async (weekNumber) => {
    const released = cohort?.released_weeks || [];
    const isReleased = released.includes(weekNumber);
    const endpoint = isReleased ? 'unrelease-week' : 'release-week';
    try {
      const res = await axios.post(`${API_URL}/api/cohorts/${cohortId}/${endpoint}`, { week_number: weekNumber });
      setCohort(prev => ({ ...prev, released_weeks: res.data.released_weeks }));
      toast.success(isReleased ? `Week ${weekNumber} hidden from students` : `Week ${weekNumber} released to students`);
    } catch (error) {
      toast.error('Failed to update week visibility');
    }
  };

  const handleUploadMaterial = async () => {
    if (!materialForm.title.trim() || !materialForm.file) { toast.error('Please provide title and file'); return; }
    setUploadingMaterial(true);
    try {
      const formData = new FormData();
      formData.append('file', materialForm.file);
      const params = new URLSearchParams({
        week_number: materialForm.week_number, material_type: materialForm.material_type,
        title: materialForm.title, description: materialForm.description, due_date: materialForm.due_date || '',
        feedback_template: materialForm.material_type === 'homework' ? (materialForm.feedback_template || '') : '',
        submission_type: materialForm.material_type === 'homework' ? (materialForm.submission_type || '') : '',
        questionnaire_fields: (materialForm.material_type === 'homework' && materialForm.submission_type === 'business_questionnaire')
          ? JSON.stringify(materialForm.questionnaire_fields || [])
          : ''
      });
      await axios.post(`${API_URL}/api/cohorts/${cohortId}/materials?${params}`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Material uploaded');
      setShowUploadMaterial(false);
      setMaterialForm({ title: '', description: '', week_number: 1, material_type: 'workbook', file: null, due_date: '', feedback_template: '', submission_type: '', questionnaire_fields: [] });
      fetchCohort();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to upload material');
    } finally {
      setUploadingMaterial(false);
    }
  };

  const handleDeleteMaterial = async (materialId) => {
    if (!window.confirm('Delete this material?')) return;
    try {
      await axios.delete(`${API_URL}/api/materials/${materialId}`);
      toast.success('Material deleted');
      fetchCohort();
    } catch (error) {
      toast.error('Failed to delete material');
    }
  };

  const handleSubmitHomework = async () => {
    if (!homeworkFile) { toast.error('Please select a file'); return; }
    setSubmittingHomework(true);
    try {
      const formData = new FormData();
      formData.append('file', homeworkFile);
      await axios.post(`${API_URL}/api/materials/${selectedHomework.material_id}/submit`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Homework submitted! Your instructor will review it soon.');
      setShowSubmitHomework(false);
      setSelectedHomework(null);
      setHomeworkFile(null);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to submit homework');
    } finally {
      setSubmittingHomework(false);
    }
  };

  const handleSubmitOnBehalf = async ({ studentId, materialId, file }) => {
    setSubmittingOnBehalf(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('student_id', studentId);
      formData.append('cohort_id', cohortId);
      const res = await axios.post(`${API_URL}/api/materials/${materialId}/submit-on-behalf`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(res.data.message);
      setShowSubmitOnBehalf(false);
      fetchCohort();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to submit on behalf');
    } finally {
      setSubmittingOnBehalf(false);
    }
  };

  const handleDownloadMaterial = async (materialId, fileName) => {
    const token = localStorage.getItem('thinkific_session_token');
    if (!token) { toast.error('Please log in to download files'); return; }
    try {
      const response = await fetch(`${API_URL}/api/materials/${materialId}/download?token=${encodeURIComponent(token)}`);
      if (!response.ok) throw new Error(await response.text() || 'Download failed');
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = fileName || 'material';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      toast.error('Failed to download file');
    }
  };

  const handleDownloadTemplate = async () => {
    const token = localStorage.getItem('thinkific_session_token');
    if (!token) { toast.error('Please log in to download files'); return; }
    try {
      const response = await fetch(`${API_URL}/api/cohorts/${cohortId}/students/template?token=${encodeURIComponent(token)}`);
      if (!response.ok) throw new Error(await response.text() || 'Download failed');
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = 'student_import_template.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      toast.error('Failed to download template');
    }
  };

  const handleBulkImport = async () => {
    if (!bulkFile) { toast.error('Please select a CSV file'); return; }
    setImportingBulk(true);
    setImportResults(null);
    try {
      const formData = new FormData();
      formData.append('file', bulkFile);
      const response = await axios.post(`${API_URL}/api/cohorts/${cohortId}/students/bulk`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      setImportResults(response.data.results);
      toast.success(response.data.message);
      fetchCohort();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Import failed');
    } finally {
      setImportingBulk(false);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-[#E1F0FF] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#22438E] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#E1F0FF]" data-testid="cohort-detail-page">
      {/* Header */}
      <header className="bg-white border-b border-[#B8D4E8]">
        <div className="max-w-7xl mx-auto px-6 md:px-12 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/dashboard">
              <Button variant="ghost" size="icon" className="rounded-full">
                <ArrowLeft className="w-5 h-5" />
              </Button>
            </Link>
            <div>
              <h1 className="text-2xl font-light text-[#000000]" data-testid="cohort-name">{cohort?.name}</h1>
              <p className="text-sm text-[#666666]">
                {cohort?.student_ids?.length || 0} students · {materials.reduce((a, w) => a + (w.workbooks?.length || 0) + (w.case_studies?.length || 0) + (w.homework?.length || 0), 0)} materials
              </p>
            </div>
          </div>
          
          {isInstructor && (
            <div className="flex items-center gap-2">
              {isSuperAdmin && (
                <Button variant="outline" onClick={() => setShowAssignInstructor(true)}
                  className="border-[#22438E] text-[#22438E] hover:bg-[#E1F0FF] rounded-lg" data-testid="assign-instructor-btn">
                  <UserCog className="w-4 h-4 mr-2" />Assign Instructor
                </Button>
              )}
              <Button variant="outline" onClick={() => setShowInviteLink(true)}
                className="border-[#1A75BA] text-[#1A75BA] hover:bg-[#E1F0FF] rounded-lg" data-testid="invite-link-btn">
                <QrCode className="w-4 h-4 mr-2" />Invite Link
              </Button>
              <Button variant="outline" onClick={() => setShowBulkImport(true)}
                className="border-[#B8D4E8] rounded-lg" data-testid="bulk-import-btn">
                <FileUp className="w-4 h-4 mr-2" />Bulk Import
              </Button>
              <Button variant="outline" onClick={() => setShowAddStudent(true)}
                className="border-[#B8D4E8] rounded-lg" data-testid="add-student-btn">
                <UserPlus className="w-4 h-4 mr-2" />Add Student
              </Button>
              <Button onClick={() => setShowUploadMaterial(true)}
                className="bg-[#22438E] text-white hover:bg-[#1A3A7A] rounded-lg" data-testid="upload-material-btn">
                <Upload className="w-4 h-4 mr-2" />Upload Material
              </Button>
              <Button variant="outline" onClick={() => setShowSubmitOnBehalf(true)}
                className="border-[#22438E] text-[#22438E] hover:bg-[#E1F0FF] rounded-lg" data-testid="submit-on-behalf-trigger-btn">
                <FileText className="w-4 h-4 mr-2" />Submit for Student
              </Button>
            </div>
          )}
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        <Tabs defaultValue="materials" className="space-y-6">
          <TabsList className="bg-[#D0E6F9]">
            <TabsTrigger value="materials" className="data-[state=active]:bg-white">
              <FileText className="w-4 h-4 mr-2" />Materials
            </TabsTrigger>
            {isInstructor && (
              <TabsTrigger value="students" className="data-[state=active]:bg-white">
                <Users className="w-4 h-4 mr-2" />Students ({cohort?.student_ids?.length || 0})
              </TabsTrigger>
            )}
            {isInstructor && (
              <TabsTrigger value="feedback" className="data-[state=active]:bg-white" data-testid="feedback-tab-trigger">
                <MessageCircle className="w-4 h-4 mr-2" />Feedback ({cohortSubmissions.length})
              </TabsTrigger>
            )}
            {isInstructor && (
              <TabsTrigger value="insights" className="data-[state=active]:bg-white" data-testid="insights-tab-trigger">
                <BookOpen className="w-4 h-4 mr-2" />Coach Max Insights
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="materials" className="space-y-8">
            <MaterialsTab
              materials={materials} cohort={cohort} isInstructor={isInstructor}
              cohortSubmissions={cohortSubmissions}
              onDownloadMaterial={handleDownloadMaterial}
              onDeleteMaterial={handleDeleteMaterial}
              onSelectHomework={(mat) => { setSelectedHomework(mat); setShowSubmitHomework(true); }}
              onToggleWeek={handleToggleWeek}
              onUploadMaterial={() => setShowUploadMaterial(true)}
            />
          </TabsContent>

          {isInstructor && (
            <TabsContent value="students">
              <StudentsTab
                cohort={cohort} invitingAll={invitingAll}
                onInviteAll={handleInviteAll}
                onAddStudent={() => setShowAddStudent(true)}
                onRemoveStudent={handleRemoveStudent}
              />
            </TabsContent>
          )}

          {isInstructor && (
            <TabsContent value="feedback">
              <FeedbackTab
                cohortSubmissions={cohortSubmissions}
                materials={materials}
                onRefresh={fetchCohort}
              />
            </TabsContent>
          )}

          {isInstructor && (
            <TabsContent value="insights">
              <CoachMaxInsightsTab cohortId={cohortId} />
            </TabsContent>
          )}
        </Tabs>
      </main>

      {/* Dialogs */}
      <AddStudentDialog open={showAddStudent} onOpenChange={setShowAddStudent}
        studentEmail={studentEmail} setStudentEmail={setStudentEmail}
        studentName={studentName} setStudentName={setStudentName}
        addingStudent={addingStudent} onSubmit={handleAddStudent} />

      <UploadMaterialDialog open={showUploadMaterial} onOpenChange={setShowUploadMaterial}
        materialForm={materialForm} setMaterialForm={setMaterialForm}
        uploadingMaterial={uploadingMaterial} onSubmit={handleUploadMaterial} />

      <SubmitHomeworkDialog open={showSubmitHomework} onOpenChange={setShowSubmitHomework}
        selectedHomework={selectedHomework} homeworkFile={homeworkFile} setHomeworkFile={setHomeworkFile}
        submittingHomework={submittingHomework} onSubmit={handleSubmitHomework} />

      <BulkImportDialog open={showBulkImport} onOpenChange={setShowBulkImport}
        bulkFile={bulkFile} setBulkFile={setBulkFile} importingBulk={importingBulk}
        importResults={importResults} onSubmit={handleBulkImport}
        onDownloadTemplate={handleDownloadTemplate}
        onClose={() => { setBulkFile(null); setImportResults(null); }} />

      <InviteLinkDialog open={showInviteLink} onOpenChange={setShowInviteLink}
        cohort={cohort} copied={copied} setCopied={setCopied} />

      <AssignInstructorDialog open={showAssignInstructor} onOpenChange={setShowAssignInstructor}
        cohort={cohort} instructorsList={instructorsList} onAssign={handleAssignInstructor} />
      <SubmitOnBehalfDialog open={showSubmitOnBehalf} onOpenChange={setShowSubmitOnBehalf}
        cohort={cohort} submitting={submittingOnBehalf} onSubmit={handleSubmitOnBehalf}
        homeworkList={materials.flatMap(week => week.homework || [])} />
    </div>
  );
}
