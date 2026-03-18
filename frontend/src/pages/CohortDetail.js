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
  Clock
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function CohortDetail() {
  const { cohortId } = useParams();
  const navigate = useNavigate();
  const { user, isInstructor, loading: authLoading } = useAuth();
  
  const [cohort, setCohort] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Dialogs
  const [showAddStudent, setShowAddStudent] = useState(false);
  const [showUploadMaterial, setShowUploadMaterial] = useState(false);
  const [showSubmitHomework, setShowSubmitHomework] = useState(false);
  const [showBulkImport, setShowBulkImport] = useState(false);
  
  // Form states
  const [studentEmail, setStudentEmail] = useState('');
  const [addingStudent, setAddingStudent] = useState(false);
  
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
      const [cohortRes, materialsRes] = await Promise.all([
        axios.get(`${API_URL}/api/cohorts/${cohortId}`, { withCredentials: true }),
        axios.get(`${API_URL}/api/cohorts/${cohortId}/materials`, { withCredentials: true })
      ]);
      setCohort(cohortRes.data);
      setMaterials(materialsRes.data);
    } catch (error) {
      console.error('Error fetching cohort:', error);
      toast.error('Failed to load cohort');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [cohortId, navigate]);

  useEffect(() => {
    if (!authLoading && user) {
      fetchCohort();
    }
  }, [authLoading, user, fetchCohort]);

  const handleAddStudent = async () => {
    if (!studentEmail.trim()) {
      toast.error('Please enter student email');
      return;
    }

    setAddingStudent(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/cohorts/${cohortId}/students`,
        { email: studentEmail },
        { withCredentials: true }
      );
      toast.success(`${res.data.student.name} added to cohort`);
      setShowAddStudent(false);
      setStudentEmail('');
      fetchCohort();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add student');
    } finally {
      setAddingStudent(false);
    }
  };

  const handleRemoveStudent = async (studentId, studentName) => {
    if (!window.confirm(`Remove ${studentName} from this cohort?`)) return;

    try {
      await axios.delete(
        `${API_URL}/api/cohorts/${cohortId}/students/${studentId}`,
        { withCredentials: true }
      );
      toast.success('Student removed');
      fetchCohort();
    } catch (error) {
      toast.error('Failed to remove student');
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
          withCredentials: true,
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
      await axios.delete(`${API_URL}/api/materials/${materialId}`, { withCredentials: true });
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
          withCredentials: true,
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
    try {
      const response = await axios.get(
        `${API_URL}/api/materials/${materialId}/download`,
        { 
          withCredentials: true,
          responseType: 'blob'
        }
      );
      
      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', fileName);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      
      toast.success('Download started');
    } catch (error) {
      toast.error('Failed to download file');
    }
  };

  const handleDownloadTemplate = async () => {
    try {
      const response = await axios.get(
        `${API_URL}/api/cohorts/${cohortId}/students/template`,
        { 
          withCredentials: true,
          responseType: 'blob'
        }
      );
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'student_import_template.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
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
          withCredentials: true,
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
              <p className="text-sm text-[#888]">{cohort?.description || 'No description'}</p>
            </div>
          </div>
          
          {isInstructor && (
            <div className="flex items-center gap-2">
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
                            <div className="flex items-center justify-between">
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
              Enter the student's email address. They must have already signed up.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="student-email">Student Email</Label>
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
              {addingStudent ? 'Adding...' : 'Add Student'}
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
              <div className="mt-1 upload-zone rounded-lg p-6 text-center cursor-pointer"
                onClick={() => document.getElementById('material-file').click()}
              >
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
              </div>
              <input
                id="material-file"
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
            <div className="mt-1 upload-zone rounded-lg p-8 text-center cursor-pointer"
              onClick={() => document.getElementById('homework-file').click()}
            >
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
            </div>
            <input
              id="homework-file"
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
              <div className="mt-1 upload-zone rounded-lg p-6 text-center cursor-pointer"
                onClick={() => document.getElementById('bulk-file').click()}
              >
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
              </div>
              <input
                id="bulk-file"
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
    </div>
  );
}
