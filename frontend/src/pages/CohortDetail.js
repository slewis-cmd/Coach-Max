import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogHeader, 
  DialogTitle,
  DialogFooter
} from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { QRCodeSVG } from 'qrcode.react';
import { 
  BookOpen, 
  Users, 
  FileText, 
  Plus, 
  ArrowLeft,
  Upload,
  Trash2,
  UserPlus,
  File,
  BookMarked,
  ClipboardList,
  X,
  Download,
  FileUp,
  CheckCircle,
  AlertCircle,
  Calendar,
  Clock,
  Eye,
  EyeOff,
  Mail,
  QrCode,
  Copy,
  Check,
  UserCog
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const downloadFile = async (url, filename) => {
  const token = localStorage.getItem('thinkific_session_token');
  if (!token) {
    toast.error('Please log in to download files');
    return;
  }
  const separator = url.includes('?') ? '&' : '?';
  try {
    const response = await fetch(`${url}${separator}token=${encodeURIComponent(token)}`);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || 'Download failed');
    }
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename || 'download';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(blobUrl);
  } catch (err) {
    console.error('Download error:', err);
    toast.error('Failed to download file');
  }
};

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
  const [instructorsList, setInstructorsList] = useState([]);
  const [assigningInstructor, setAssigningInstructor] = useState(false);
  
  // Form states
  const [studentEmail, setStudentEmail] = useState('');
  const [studentName, setStudentName] = useState('');
  const [addingStudent, setAddingStudent] = useState(false);
  const [invitingAll, setInvitingAll] = useState(false);
  
  const [materialForm, setMaterialForm] = useState({
    title: '',
    description: '',
    week_number: 1,
    material_type: 'workbook',
    file: null,
    due_date: ''
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
      // Instructors/admins also fetch submissions
      if (isInstructor) {
        requests.push(
          axios.get(`${API_URL}/api/cohorts/${cohortId}/submissions`).catch(() => ({ data: [] }))
        );
      }
      const results = await Promise.all(requests);
      setCohort(results[0].data);
      setMaterials(results[1].data);
      if (results[2]) {
        setCohortSubmissions(results[2].data);
      }
    } catch (error) {
      console.error('Error fetching cohort:', error);
      toast.error('Failed to load cohort');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [cohortId, navigate, isInstructor]);

  useEffect(() => {
    if (!authLoading && user) {
      fetchCohort();
    }
  }, [authLoading, user, fetchCohort]);

  useEffect(() => {
    if (isSuperAdmin && showAssignInstructor) {
      axios.get(`${API_URL}/api/instructors`).then(res => {
        setInstructorsList(res.data);
      }).catch(() => toast.error('Failed to load instructors'));
    }
  }, [isSuperAdmin, showAssignInstructor]);

  const handleAssignInstructor = async (instructorId) => {
    setAssigningInstructor(true);
    try {
      const res = await axios.post(`${API_URL}/api/cohorts/${cohortId}/assign-instructor`, {
        instructor_id: instructorId
      });
      toast.success(res.data.message);
      setShowAssignInstructor(false);
      fetchCohort();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to assign instructor');
    } finally {
      setAssigningInstructor(false);
    }
  };

  const handleAddStudent = async () => {
    if (!studentEmail.trim()) {
      toast.error('Please enter student email');
      return;
    }

    setAddingStudent(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/cohorts/${cohortId}/students`,
        { email: studentEmail, name: studentName }
      );
      toast.success(res.data.invitation_sent 
        ? `${res.data.student.name} added — invitation email sent!` 
        : `${res.data.student.name} added to cohort`
      );
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
      const res = await axios.post(
        `${API_URL}/api/cohorts/${cohortId}/students/invite-all`,
        {}
      );
      toast.success(res.data.message);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to send invitations');
    } finally {
      setInvitingAll(false);
    }
  };

  const handleRemoveStudent = async (studentId, studentName) => {
    if (!window.confirm(`Remove ${studentName} from this cohort?`)) return;

    try {
      await axios.delete(
        `${API_URL}/api/cohorts/${cohortId}/students/${studentId}`
      );
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
      const res = await axios.post(
        `${API_URL}/api/cohorts/${cohortId}/${endpoint}`,
        { week_number: weekNumber }
      );
      setCohort(prev => ({ ...prev, released_weeks: res.data.released_weeks }));
      toast.success(isReleased ? `Week ${weekNumber} hidden from students` : `Week ${weekNumber} released to students`);
    } catch (error) {
      toast.error('Failed to update week visibility');
    }
  };

  const handleUploadMaterial = async () => {
    if (!materialForm.title.trim() || !materialForm.file) {
      toast.error('Please provide title and file');
      return;
    }

    setUploadingMaterial(true);
    try {
      const formData = new FormData();
      formData.append('file', materialForm.file);

      const params = new URLSearchParams({
        week_number: materialForm.week_number,
        material_type: materialForm.material_type,
        title: materialForm.title,
        description: materialForm.description,
        due_date: materialForm.due_date || ''
      });

      await axios.post(
        `${API_URL}/api/cohorts/${cohortId}/materials?${params}`,
        formData,
        { 
          headers: { 'Content-Type': 'multipart/form-data' }
        }
      );
      
      toast.success('Material uploaded');
      setShowUploadMaterial(false);
      setMaterialForm({ title: '', description: '', week_number: 1, material_type: 'workbook', file: null, due_date: '' });
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
    if (!homeworkFile) {
      toast.error('Please select a file');
      return;
    }

    setSubmittingHomework(true);
    try {
      const formData = new FormData();
      formData.append('file', homeworkFile);

      await axios.post(
        `${API_URL}/api/materials/${selectedHomework.material_id}/submit`,
        formData,
        { 
          headers: { 'Content-Type': 'multipart/form-data' }
        }
      );
      
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

  const handleDownloadMaterial = async (materialId, fileName) => {
    const token = localStorage.getItem('thinkific_session_token');
    if (!token) {
      toast.error('Please log in to download files');
      return;
    }
    try {
      const response = await fetch(`${API_URL}/api/materials/${materialId}/download?token=${encodeURIComponent(token)}`);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || 'Download failed');
      }
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
      console.error('Download error:', err);
      toast.error('Failed to download file');
    }
  };

  const handleDownloadTemplate = async () => {
    const token = localStorage.getItem('thinkific_session_token');
    if (!token) {
      toast.error('Please log in to download files');
      return;
    }
    try {
      const response = await fetch(`${API_URL}/api/cohorts/${cohortId}/students/template?token=${encodeURIComponent(token)}`);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || 'Download failed');
      }
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
      console.error('Download error:', err);
      toast.error('Failed to download template');
    }
  };

  const handleBulkImport = async () => {
    if (!bulkFile) {
      toast.error('Please select a CSV file');
      return;
    }

    setImportingBulk(true);
    setImportResults(null);
    
    try {
      const formData = new FormData();
      formData.append('file', bulkFile);

      const response = await axios.post(
        `${API_URL}/api/cohorts/${cohortId}/students/bulk`,
        formData,
        { 
          headers: { 'Content-Type': 'multipart/form-data' }
        }
      );
      
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
      <div className="min-h-screen bg-[#F9F8F6] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#1A1A1A] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6]" data-testid="cohort-detail">
      {/* Header */}
      <header className="bg-white border-b border-[#E5E5E5] sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link 
              to="/dashboard"
              className="p-2 hover:bg-[#F2F0ED] rounded-lg transition-colors"
              data-testid="back-to-dashboard"
            >
              <ArrowLeft className="w-5 h-5 text-[#5A5A5A]" />
            </Link>
            <div>
              <h1 className="text-lg font-medium text-[#1A1A1A]">{cohort?.name}</h1>
              <p className="text-sm text-[#888]">
                {cohort?.instructor_name ? `Instructor: ${cohort.instructor_name}` : (cohort?.description || 'No description')}
              </p>
            </div>
          </div>
          
          {isInstructor && (
            <div className="flex items-center gap-2">
              {isSuperAdmin && (
                <Button 
                  variant="outline"
                  onClick={() => setShowAssignInstructor(true)}
                  className="border-[#7C3AED] text-[#7C3AED] hover:bg-[#F3E8FF] rounded-lg"
                  data-testid="assign-instructor-btn"
                >
                  <UserCog className="w-4 h-4 mr-2" />
                  Assign Instructor
                </Button>
              )}
              <Button 
                variant="outline"
                onClick={() => setShowInviteLink(true)}
                className="border-[#065F46] text-[#065F46] hover:bg-[#D1FAE5] rounded-lg"
                data-testid="invite-link-btn"
              >
                <QrCode className="w-4 h-4 mr-2" />
                Invite Link
              </Button>
              <Button 
                variant="outline"
                onClick={() => setShowBulkImport(true)}
                className="border-[#E5E5E5] rounded-lg"
                data-testid="bulk-import-btn"
              >
                <FileUp className="w-4 h-4 mr-2" />
                Bulk Import
              </Button>
              <Button 
                variant="outline"
                onClick={() => setShowAddStudent(true)}
                className="border-[#E5E5E5] rounded-lg"
                data-testid="add-student-btn"
              >
                <UserPlus className="w-4 h-4 mr-2" />
                Add Student
              </Button>
              <Button 
                onClick={() => setShowUploadMaterial(true)}
                className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
                data-testid="upload-material-btn"
              >
                <Upload className="w-4 h-4 mr-2" />
                Upload Material
              </Button>
            </div>
          )}
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-6 md:px-12 py-8">
        <Tabs defaultValue="materials" className="space-y-6">
          <TabsList className="bg-[#F2F0ED]">
            <TabsTrigger value="materials" className="data-[state=active]:bg-white">
              <FileText className="w-4 h-4 mr-2" />
              Materials
            </TabsTrigger>
            {isInstructor && (
              <TabsTrigger value="students" className="data-[state=active]:bg-white">
                <Users className="w-4 h-4 mr-2" />
                Students ({cohort?.student_ids?.length || 0})
              </TabsTrigger>
            )}
          </TabsList>

          {/* Materials Tab */}
          <TabsContent value="materials" className="space-y-8">
            {materials.length === 0 ? (
              <Card className="bg-white border-[#E5E5E5] border-dashed">
                <CardContent className="p-12 text-center">
                  <FileText className="w-12 h-12 text-[#C4C4C4] mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">No materials yet</h3>
                  <p className="text-[#5A5A5A] mb-4">
                    {isInstructor ? 'Upload your first workbook, case study, or homework assignment' : 'Your instructor will upload materials soon'}
                  </p>
                  {isInstructor && (
                    <Button 
                      onClick={() => setShowUploadMaterial(true)}
                      className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
                    >
                      Upload Material
                    </Button>
                  )}
                </CardContent>
              </Card>
            ) : (
              materials.sort((a, b) => a.week_number - b.week_number).map((week) => (
                <div key={week.week_number} className="space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-[#1A1A1A] text-white rounded-full flex items-center justify-center font-medium">
                      {week.week_number}
                    </div>
                    <h2 className="text-xl font-light text-[#1A1A1A]">Week {week.week_number}</h2>
                    {isInstructor && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleWeek(week.week_number)}
                        className={`ml-auto rounded-lg text-xs ${
                          (cohort?.released_weeks || []).includes(week.week_number)
                            ? 'text-[#065F46] hover:bg-[#D1FAE5]'
                            : 'text-[#888] hover:bg-[#F2F0ED]'
                        }`}
                        data-testid={`toggle-week-${week.week_number}`}
                      >
                        {(cohort?.released_weeks || []).includes(week.week_number) ? (
                          <>
                            <Eye className="w-4 h-4 mr-1.5" />
                            Visible to students
                          </>
                        ) : (
                          <>
                            <EyeOff className="w-4 h-4 mr-1.5" />
                            Hidden from students
                          </>
                        )}
                      </Button>
                    )}
                  </div>

                  <div className="grid md:grid-cols-3 gap-4 pl-12">
                    {/* Workbooks */}
                    {week.workbooks?.map((mat) => (
                      <Card key={mat.material_id} className="bg-white border-[#E5E5E5] group">
                        <CardHeader className="pb-2">
                          <div className="flex items-start justify-between">
                            <div className="w-10 h-10 bg-[#E0F2FE] rounded-lg flex items-center justify-center">
                              <BookMarked className="w-5 h-5 text-[#075985]" />
                            </div>
                            <div className="flex items-center gap-1">
                              <Button 
                                variant="ghost" 
                                size="icon"
                                className="opacity-0 group-hover:opacity-100 transition-opacity"
                                onClick={() => handleDownloadMaterial(mat.material_id, mat.file_name)}
                                data-testid={`download-${mat.material_id}`}
                              >
                                <Download className="w-4 h-4 text-[#075985]" />
                              </Button>
                              {isInstructor && (
                                <Button 
                                  variant="ghost" 
                                  size="icon"
                                  className="opacity-0 group-hover:opacity-100 transition-opacity"
                                  onClick={() => handleDeleteMaterial(mat.material_id)}
                                >
                                  <Trash2 className="w-4 h-4 text-red-500" />
                                </Button>
                              )}
                            </div>
                          </div>
                          <CardTitle className="text-base font-medium mt-2">{mat.title}</CardTitle>
                          <CardDescription className="text-xs uppercase tracking-wide">Workbook</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <p className="text-sm text-[#5A5A5A] mb-3">{mat.description || 'No description'}</p>
                          <div className="flex items-center justify-between">
                            <p className="text-xs text-[#888]">
                              <File className="w-3 h-3 inline mr-1" />
                              {mat.file_name}
                            </p>
                            <Button 
                              variant="ghost" 
                              size="sm"
                              className="text-[#075985] hover:text-[#064E3B] h-7 px-2"
                              onClick={() => handleDownloadMaterial(mat.material_id, mat.file_name)}
                            >
                              <Download className="w-3 h-3 mr-1" />
                              Download
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    ))}

                    {/* Case Studies */}
                    {week.case_studies?.map((mat) => (
                      <Card key={mat.material_id} className="bg-white border-[#E5E5E5] group">
                        <CardHeader className="pb-2">
                          <div className="flex items-start justify-between">
                            <div className="w-10 h-10 bg-[#FDE047] rounded-lg flex items-center justify-center">
                              <ClipboardList className="w-5 h-5 text-[#1A1A1A]" />
                            </div>
                            <div className="flex items-center gap-1">
                              <Button 
                                variant="ghost" 
                                size="icon"
                                className="opacity-0 group-hover:opacity-100 transition-opacity"
                                onClick={() => handleDownloadMaterial(mat.material_id, mat.file_name)}
                                data-testid={`download-${mat.material_id}`}
                              >
                                <Download className="w-4 h-4 text-[#854D0E]" />
                              </Button>
                              {isInstructor && (
                                <Button 
                                  variant="ghost" 
                                  size="icon"
                                  className="opacity-0 group-hover:opacity-100 transition-opacity"
                                  onClick={() => handleDeleteMaterial(mat.material_id)}
                                >
                                  <Trash2 className="w-4 h-4 text-red-500" />
                                </Button>
                              )}
                            </div>
                          </div>
                          <CardTitle className="text-base font-medium mt-2">{mat.title}</CardTitle>
                          <CardDescription className="text-xs uppercase tracking-wide">Case Study</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <p className="text-sm text-[#5A5A5A] mb-3">{mat.description || 'No description'}</p>
                          <div className="flex items-center justify-between">
                            <p className="text-xs text-[#888]">
                              <File className="w-3 h-3 inline mr-1" />
                              {mat.file_name}
                            </p>
                            <Button 
                              variant="ghost" 
                              size="sm"
                              className="text-[#854D0E] hover:text-[#713F12] h-7 px-2"
                              onClick={() => handleDownloadMaterial(mat.material_id, mat.file_name)}
                            >
                              <Download className="w-3 h-3 mr-1" />
                              Download
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    ))}

                    {/* Homework */}
                    {week.homework?.map((mat) => (
                      <Card key={mat.material_id} className="bg-white border-[#E5E5E5] group">
                        <CardHeader className="pb-2">
                          <div className="flex items-start justify-between">
                            <div className="w-10 h-10 bg-[#D1FAE5] rounded-lg flex items-center justify-center">
                              <Upload className="w-5 h-5 text-[#065F46]" />
                            </div>
                            <div className="flex items-center gap-1">
                              <Button 
                                variant="ghost" 
                                size="icon"
                                className="opacity-0 group-hover:opacity-100 transition-opacity"
                                onClick={() => handleDownloadMaterial(mat.material_id, mat.file_name)}
                                data-testid={`download-${mat.material_id}`}
                              >
                                <Download className="w-4 h-4 text-[#065F46]" />
                              </Button>
                              {isInstructor && (
                                <Button 
                                  variant="ghost" 
                                  size="icon"
                                  className="opacity-0 group-hover:opacity-100 transition-opacity"
                                  onClick={() => handleDeleteMaterial(mat.material_id)}
                                >
                                  <Trash2 className="w-4 h-4 text-red-500" />
                                </Button>
                              )}
                            </div>
                          </div>
                          <CardTitle className="text-base font-medium mt-2">{mat.title}</CardTitle>
                          <CardDescription className="text-xs uppercase tracking-wide">Homework Assignment</CardDescription>
                          {mat.due_date && (
                            <div className={`flex items-center gap-1 mt-2 text-xs ${
                              new Date(mat.due_date) < new Date() ? 'text-red-500' : 'text-[#854D0E]'
                            }`}>
                              <Calendar className="w-3 h-3" />
                              Due: {new Date(mat.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                              {new Date(mat.due_date) < new Date() && ' (Past due)'}
                            </div>
                          )}
                        </CardHeader>
                        <CardContent>
                          <p className="text-sm text-[#5A5A5A] mb-3">{mat.description || 'No description'}</p>
                          {!isInstructor ? (
                            <Button 
                              size="sm"
                              onClick={() => {
                                setSelectedHomework(mat);
                                setShowSubmitHomework(true);
                              }}
                              className="w-full bg-[#065F46] text-white hover:bg-[#064E3B] rounded-lg"
                              data-testid={`submit-homework-${mat.material_id}`}
                            >
                              Submit Homework
                            </Button>
                          ) : (
                            <>
                              <div className="flex items-center justify-between mb-3">
                                <p className="text-xs text-[#888]">
                                  <File className="w-3 h-3 inline mr-1" />
                                  {mat.file_name}
                                </p>
                                <Button 
                                  variant="ghost" 
                                  size="sm"
                                  className="text-[#065F46] hover:text-[#064E3B] h-7 px-2"
                                  onClick={() => handleDownloadMaterial(mat.material_id, mat.file_name)}
                                >
                                  <Download className="w-3 h-3 mr-1" />
                                  Download
                                </Button>
                              </div>
                              {/* Student Submissions */}
                              {(() => {
                                const subs = cohortSubmissions.filter(s => s.material_id === mat.material_id);
                                if (subs.length === 0) return (
                                  <p className="text-xs text-[#888] italic pt-2 border-t border-[#E5E5E5]">No submissions yet</p>
                                );
                                return (
                                  <div className="pt-2 border-t border-[#E5E5E5] space-y-2" data-testid={`submissions-${mat.material_id}`}>
                                    <p className="text-xs font-medium text-[#5A5A5A] uppercase tracking-wide">Submissions ({subs.length})</p>
                                    {subs.map(sub => (
                                      <div key={sub.submission_id} className="rounded-lg bg-[#F9F8F6] overflow-hidden" data-testid={`sub-row-${sub.submission_id}`}>
                                        <div className="flex items-center gap-2 py-2 px-3">
                                          <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-[#1A1A1A] truncate">{sub.student?.name || 'Unknown'}</p>
                                            <p className="text-xs text-[#888] truncate">{sub.file_name}</p>
                                          </div>
                                          <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${
                                            sub.status === 'sent' ? 'bg-[#D1FAE5] text-[#065F46]' :
                                            sub.status === 'draft' ? 'bg-[#F3E8FF] text-[#6B21A8]' :
                                            'bg-[#DBEAFE] text-[#1E40AF]'
                                          }`}>
                                            {sub.status === 'sent' ? 'Reviewed' : sub.status === 'draft' ? 'Draft' : 'Pending'}
                                          </span>
                                          <button
                                            onClick={() => downloadFile(
                                              `${API_URL}/api/submissions/${sub.submission_id}/download`,
                                              sub.file_name
                                            )}
                                            className="text-[#065F46] hover:text-[#064E3B] p-1 flex-shrink-0"
                                            title="Download submission"
                                            data-testid={`download-sub-${sub.submission_id}`}
                                          >
                                            <Download className="w-4 h-4" />
                                          </button>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                );
                              })()}
                            </>
                          )}
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              ))
            )}
          </TabsContent>

          {/* Students Tab (Instructor only) */}
          {isInstructor && (
            <TabsContent value="students">
              {cohort?.students?.length > 0 && (
                <div className="flex justify-end mb-4">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleInviteAll}
                    disabled={invitingAll}
                    className="border-[#1A1A1A] text-[#1A1A1A] hover:bg-[#F2F0ED] rounded-lg"
                    data-testid="invite-all-btn"
                  >
                    <Mail className="w-4 h-4 mr-1.5" />
                    {invitingAll ? 'Sending...' : 'Send Invitations to All'}
                  </Button>
                </div>
              )}
              {cohort?.students?.length === 0 ? (
                <Card className="bg-white border-[#E5E5E5] border-dashed">
                  <CardContent className="p-12 text-center">
                    <Users className="w-12 h-12 text-[#C4C4C4] mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">No students yet</h3>
                    <p className="text-[#5A5A5A] mb-4">Add students by their email address</p>
                    <Button 
                      onClick={() => setShowAddStudent(true)}
                      className="bg-[#1A1A1A] text-white hover:bg-[#333] rounded-lg"
                    >
                      Add Student
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-3">
                  {cohort?.students?.map((student) => (
                    <Card key={student.user_id} className="bg-white border-[#E5E5E5]">
                      <CardContent className="p-4 flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          {student.picture ? (
                            <img src={student.picture} alt={student.name} className="w-10 h-10 rounded-full" />
                          ) : (
                            <div className="w-10 h-10 bg-[#F2F0ED] rounded-full flex items-center justify-center">
                              <Users className="w-5 h-5 text-[#888]" />
                            </div>
                          )}
                          <div>
                            <p className="font-medium text-[#1A1A1A]">{student.name}</p>
                            <p className="text-sm text-[#888]">{student.email}</p>
                          </div>
                        </div>
                        <Button 
                          variant="ghost" 
                          size="icon"
                          onClick={() => handleRemoveStudent(student.user_id, student.name)}
                          className="text-red-500 hover:text-red-600 hover:bg-red-50"
                        >
                          <X className="w-4 h-4" />
                        </Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>
          )}
        </Tabs>
      </main>

      {/* Add Student Dialog */}
      <Dialog open={showAddStudent} onOpenChange={setShowAddStudent}>
        <DialogContent className="bg-white">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Add Student</DialogTitle>
            <DialogDescription>
              Enter the student's email. An invitation email will be sent to them.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="student-email">Student Email *</Label>
              <Input
                id="student-email"
                data-testid="student-email-input"
                type="email"
                placeholder="student@example.com"
                value={studentEmail}
                onChange={(e) => setStudentEmail(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="student-name">Student Name (optional)</Label>
              <Input
                id="student-name"
                data-testid="student-name-input"
                type="text"
                placeholder="Jane Smith"
                value={studentName}
                onChange={(e) => setStudentName(e.target.value)}
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddStudent(false)}>
              Cancel
            </Button>
            <Button 
              data-testid="add-student-submit"
              onClick={handleAddStudent}
              disabled={addingStudent}
              className="bg-[#1A1A1A] text-white hover:bg-[#333]"
            >
              {addingStudent ? 'Sending invite...' : 'Add & Invite'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload Material Dialog */}
      <Dialog open={showUploadMaterial} onOpenChange={setShowUploadMaterial}>
        <DialogContent className="bg-white max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Upload Material</DialogTitle>
            <DialogDescription>
              Upload a workbook, case study, or homework assignment.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Week Number</Label>
                <Select 
                  value={String(materialForm.week_number)}
                  onValueChange={(v) => setMaterialForm({ ...materialForm, week_number: parseInt(v) })}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[1,2,3,4,5,6,7,8,9,10,11,12].map(n => (
                      <SelectItem key={n} value={String(n)}>Week {n}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Material Type</Label>
                <Select 
                  value={materialForm.material_type}
                  onValueChange={(v) => setMaterialForm({ ...materialForm, material_type: v })}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="workbook">Workbook</SelectItem>
                    <SelectItem value="case_study">Case Study</SelectItem>
                    <SelectItem value="homework">Homework Assignment</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label htmlFor="material-title">Title</Label>
              <Input
                id="material-title"
                data-testid="material-title-input"
                placeholder="e.g., Chapter 3 Workbook"
                value={materialForm.title}
                onChange={(e) => setMaterialForm({ ...materialForm, title: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="material-desc">Description (optional)</Label>
              <Textarea
                id="material-desc"
                placeholder="Brief description..."
                value={materialForm.description}
                onChange={(e) => setMaterialForm({ ...materialForm, description: e.target.value })}
                className="mt-1"
                rows={2}
              />
            </div>
            {materialForm.material_type === 'homework' && (
              <div>
                <Label htmlFor="due-date">Due Date (optional)</Label>
                <Input
                  id="due-date"
                  type="date"
                  data-testid="due-date-input"
                  value={materialForm.due_date}
                  onChange={(e) => setMaterialForm({ ...materialForm, due_date: e.target.value })}
                  className="mt-1"
                />
              </div>
            )}
            <div>
              <Label>File (PDF or Word)</Label>
              <div className="mt-1 upload-zone rounded-lg p-6 text-center cursor-pointer">
                <label htmlFor="material-file" className="cursor-pointer block">
                  {materialForm.file ? (
                    <div className="flex items-center justify-center gap-2">
                      <File className="w-5 h-5 text-[#065F46]" />
                      <span className="text-sm text-[#1A1A1A]">{materialForm.file.name}</span>
                    </div>
                  ) : (
                    <>
                      <Upload className="w-8 h-8 text-[#C4C4C4] mx-auto mb-2" />
                      <p className="text-sm text-[#888]">Click to upload PDF or DOCX</p>
                    </>
                  )}
                </label>
              </div>
              <input
                id="material-file"
                data-testid="material-file-input"
                type="file"
                accept=".pdf,.docx"
                className="hidden"
                onChange={(e) => setMaterialForm({ ...materialForm, file: e.target.files[0] })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadMaterial(false)}>
              Cancel
            </Button>
            <Button 
              data-testid="upload-material-submit"
              onClick={handleUploadMaterial}
              disabled={uploadingMaterial}
              className="bg-[#1A1A1A] text-white hover:bg-[#333]"
            >
              {uploadingMaterial ? 'Uploading...' : 'Upload'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Submit Homework Dialog */}
      <Dialog open={showSubmitHomework} onOpenChange={setShowSubmitHomework}>
        <DialogContent className="bg-white">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Submit Homework</DialogTitle>
            <DialogDescription>
              {selectedHomework?.title}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label>Your Submission (PDF or Word)</Label>
            <div className="mt-1 upload-zone rounded-lg p-8 text-center cursor-pointer">
              <label htmlFor="homework-file" className="cursor-pointer block">
                {homeworkFile ? (
                  <div className="flex items-center justify-center gap-2">
                    <File className="w-5 h-5 text-[#065F46]" />
                    <span className="text-sm text-[#1A1A1A]">{homeworkFile.name}</span>
                  </div>
                ) : (
                  <>
                    <Upload className="w-10 h-10 text-[#C4C4C4] mx-auto mb-2" />
                    <p className="text-sm text-[#888]">Click to upload your homework</p>
                    <p className="text-xs text-[#C4C4C4] mt-1">PDF or DOCX only</p>
                  </>
                )}
              </label>
            </div>
            <input
              id="homework-file"
              data-testid="homework-file-input"
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={(e) => setHomeworkFile(e.target.files[0])}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSubmitHomework(false)}>
              Cancel
            </Button>
            <Button 
              data-testid="submit-homework-btn"
              onClick={handleSubmitHomework}
              disabled={submittingHomework}
              className="bg-[#065F46] text-white hover:bg-[#064E3B]"
            >
              {submittingHomework ? 'Submitting...' : 'Submit'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk Import Dialog */}
      <Dialog open={showBulkImport} onOpenChange={(open) => {
        setShowBulkImport(open);
        if (!open) {
          setBulkFile(null);
          setImportResults(null);
        }
      }}>
        <DialogContent className="bg-white max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Bulk Import Students</DialogTitle>
            <DialogDescription>
              Upload a CSV file with student emails. Students will be added to this cohort.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {/* Template Download */}
            <div className="flex items-center justify-between p-4 bg-[#F2F0ED] rounded-lg">
              <div>
                <p className="text-sm font-medium text-[#1A1A1A]">Need a template?</p>
                <p className="text-xs text-[#888]">Download our CSV template to get started</p>
              </div>
              <Button 
                variant="outline"
                size="sm"
                onClick={handleDownloadTemplate}
                className="border-[#E5E5E5]"
              >
                <Download className="w-4 h-4 mr-2" />
                Template
              </Button>
            </div>

            {/* File Upload */}
            <div>
              <Label>CSV File</Label>
              <div className="mt-1 upload-zone rounded-lg p-6 text-center cursor-pointer">
                <label htmlFor="bulk-file" className="cursor-pointer block">
                  {bulkFile ? (
                    <div className="flex items-center justify-center gap-2">
                      <File className="w-5 h-5 text-[#065F46]" />
                      <span className="text-sm text-[#1A1A1A]">{bulkFile.name}</span>
                    </div>
                  ) : (
                    <>
                      <FileUp className="w-8 h-8 text-[#C4C4C4] mx-auto mb-2" />
                      <p className="text-sm text-[#888]">Click to upload CSV file</p>
                      <p className="text-xs text-[#C4C4C4] mt-1">Required column: email</p>
                    </>
                  )}
                </label>
              </div>
              <input
                id="bulk-file"
                data-testid="bulk-file-input"
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => setBulkFile(e.target.files[0])}
              />
            </div>

            {/* Import Results */}
            {importResults && (
              <div className="space-y-3">
                {importResults.added?.length > 0 && (
                  <div className="flex items-start gap-2 p-3 bg-[#D1FAE5] rounded-lg">
                    <CheckCircle className="w-4 h-4 text-[#065F46] mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-[#065F46]">
                        {importResults.added.length} students added
                      </p>
                      <p className="text-xs text-[#065F46]">
                        {importResults.added.map(s => s.name || s.email).join(', ')}
                      </p>
                    </div>
                  </div>
                )}
                {importResults.already_enrolled?.length > 0 && (
                  <div className="flex items-start gap-2 p-3 bg-[#FEF9C3] rounded-lg">
                    <AlertCircle className="w-4 h-4 text-[#854D0E] mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-[#854D0E]">
                        {importResults.already_enrolled.length} already enrolled
                      </p>
                      <p className="text-xs text-[#854D0E]">
                        {importResults.already_enrolled.join(', ')}
                      </p>
                    </div>
                  </div>
                )}
                {importResults.not_found?.length > 0 && (
                  <div className="flex items-start gap-2 p-3 bg-[#FEE2E2] rounded-lg">
                    <AlertCircle className="w-4 h-4 text-red-600 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-red-600">
                        {importResults.not_found.length} not found
                      </p>
                      <p className="text-xs text-red-600">
                        {importResults.not_found.join(', ')} (not registered yet)
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setShowBulkImport(false);
              setBulkFile(null);
              setImportResults(null);
            }}>
              {importResults ? 'Close' : 'Cancel'}
            </Button>
            {!importResults && (
              <Button 
                data-testid="bulk-import-submit"
                onClick={handleBulkImport}
                disabled={importingBulk || !bulkFile}
                className="bg-[#1A1A1A] text-white hover:bg-[#333]"
              >
                {importingBulk ? 'Importing...' : 'Import Students'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Invite Link / QR Code Dialog */}
      <Dialog open={showInviteLink} onOpenChange={setShowInviteLink}>
        <DialogContent className="bg-white max-w-sm">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Invite Students</DialogTitle>
            <DialogDescription>
              Share this link or QR code so students can join {cohort?.name}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4 space-y-6">
            {/* QR Code */}
            <div className="flex justify-center">
              <div className="bg-white p-4 rounded-xl border border-[#E5E5E5]">
                <QRCodeSVG
                  value={`${window.location.origin}/invite/${cohort?.invite_code}`}
                  size={200}
                  level="M"
                  data-testid="invite-qr-code"
                />
              </div>
            </div>

            {/* Invite URL */}
            <div>
              <Label className="text-xs text-[#888] uppercase tracking-wide">Invite Link</Label>
              <div className="mt-1 flex items-center gap-2">
                <input
                  readOnly
                  value={`${window.location.origin}/invite/${cohort?.invite_code}`}
                  className="flex-1 px-3 py-2 bg-[#F2F0ED] rounded-lg text-sm text-[#1A1A1A] border-0 outline-none"
                  data-testid="invite-url-input"
                />
                <Button
                  variant="outline"
                  size="icon"
                  className="flex-shrink-0 rounded-lg"
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/invite/${cohort?.invite_code}`);
                    setCopied(true);
                    toast.success('Link copied!');
                    setTimeout(() => setCopied(false), 2000);
                  }}
                  data-testid="copy-invite-link"
                >
                  {copied ? <Check className="w-4 h-4 text-[#065F46]" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowInviteLink(false)} className="rounded-lg">
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Assign Instructor Dialog */}
      <Dialog open={showAssignInstructor} onOpenChange={setShowAssignInstructor}>
        <DialogContent className="bg-white">
          <DialogHeader>
            <DialogTitle className="font-normal text-2xl">Assign Instructor</DialogTitle>
            <DialogDescription>
              Choose an instructor to manage this cohort. They will be able to see submissions and track student progress.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-4 max-h-[400px] overflow-y-auto">
            {instructorsList.length === 0 ? (
              <p className="text-sm text-[#888] text-center py-4">No instructors found. Promote a user to instructor first.</p>
            ) : (
              instructorsList.map((inst) => (
                <div 
                  key={inst.user_id}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    cohort?.instructor_id === inst.user_id 
                      ? 'border-[#7C3AED] bg-[#F3E8FF]' 
                      : 'border-[#E5E5E5] hover:bg-[#F9F8F6]'
                  }`}
                  onClick={() => {
                    if (cohort?.instructor_id !== inst.user_id) {
                      handleAssignInstructor(inst.user_id);
                    }
                  }}
                  data-testid={`assign-instructor-${inst.user_id}`}
                >
                  <div className="w-10 h-10 bg-[#F2F0ED] rounded-full flex items-center justify-center flex-shrink-0">
                    {inst.picture ? (
                      <img src={inst.picture} alt={inst.name} className="w-10 h-10 rounded-full" />
                    ) : (
                      <UserCog className="w-5 h-5 text-[#888]" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-[#1A1A1A] truncate">{inst.name}</p>
                    <p className="text-xs text-[#888] truncate">{inst.email}</p>
                  </div>
                  {cohort?.instructor_id === inst.user_id && (
                    <span className="text-xs bg-[#7C3AED] text-white px-2 py-0.5 rounded-full flex-shrink-0">Current</span>
                  )}
                  {inst.role === 'super_admin' && (
                    <span className="text-xs bg-[#1A1A1A] text-white px-2 py-0.5 rounded-full flex-shrink-0">Admin</span>
                  )}
                </div>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAssignInstructor(false)} className="rounded-lg">
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
