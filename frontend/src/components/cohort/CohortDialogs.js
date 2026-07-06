import React from 'react';
import { Button } from '../ui/button';
import { 
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter 
} from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { QRCodeSVG } from 'qrcode.react';
import { 
  Upload, File, FileUp, Download, CheckCircle, AlertCircle, Copy, Check, UserCog 
} from 'lucide-react';
import { toast } from 'sonner';

export function AddStudentDialog({ open, onOpenChange, studentEmail, setStudentEmail, studentName, setStudentName, addingStudent, onSubmit }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Add Student</DialogTitle>
          <DialogDescription>Enter the student's email. An invitation email will be sent to them.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label htmlFor="student-email">Student Email *</Label>
            <Input id="student-email" data-testid="student-email-input" type="email" placeholder="student@example.com"
              value={studentEmail} onChange={(e) => setStudentEmail(e.target.value)} className="mt-1" />
          </div>
          <div>
            <Label htmlFor="student-name">Student Name (optional)</Label>
            <Input id="student-name" data-testid="student-name-input" type="text" placeholder="Jane Smith"
              value={studentName} onChange={(e) => setStudentName(e.target.value)} className="mt-1" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="add-student-submit" onClick={onSubmit} disabled={addingStudent}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">
            {addingStudent ? 'Sending invite...' : 'Add & Invite'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function UploadMaterialDialog({ open, onOpenChange, materialForm, setMaterialForm, uploadingMaterial, onSubmit }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Upload Material</DialogTitle>
          <DialogDescription>Upload a workbook, case study, or homework assignment.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Week Number</Label>
              <Select value={String(materialForm.week_number)}
                onValueChange={(v) => setMaterialForm({ ...materialForm, week_number: parseInt(v) })}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {[1,2,3,4,5,6,7,8,9,10,11,12,13,14].map(n => (
                    <SelectItem key={n} value={String(n)}>Week {n}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Material Type</Label>
              <Select value={materialForm.material_type}
                onValueChange={(v) => setMaterialForm({ ...materialForm, material_type: v })}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
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
            <Input id="material-title" data-testid="material-title-input" placeholder="e.g., Chapter 3 Workbook"
              value={materialForm.title} onChange={(e) => setMaterialForm({ ...materialForm, title: e.target.value })} className="mt-1" />
          </div>
          <div>
            <Label htmlFor="material-desc">Description (optional)</Label>
            <Textarea id="material-desc" placeholder="Brief description..."
              value={materialForm.description} onChange={(e) => setMaterialForm({ ...materialForm, description: e.target.value })}
              className="mt-1" rows={2} />
          </div>
          {materialForm.material_type === 'homework' && (
            <div>
              <Label htmlFor="due-date">Due Date (optional)</Label>
              <Input id="due-date" type="date" data-testid="due-date-input"
                value={materialForm.due_date} onChange={(e) => setMaterialForm({ ...materialForm, due_date: e.target.value })} className="mt-1" />
            </div>
          )}
          {materialForm.material_type === 'homework' && (
            <div>
              <Label htmlFor="feedback-template">AI Feedback Instructions (optional)</Label>
              <Textarea id="feedback-template" data-testid="feedback-template-input"
                placeholder="Override the default rubric. e.g., 'Grade specifically on how the submission compares to the Kawasaki Model on slide 4.'"
                value={materialForm.feedback_template || ''}
                onChange={(e) => setMaterialForm({ ...materialForm, feedback_template: e.target.value })}
                className="mt-1" rows={3} />
              <p className="text-xs text-[#666666] mt-1">
                Leave blank for the default (3 things done well / 3 areas to improve). Custom instructions replace the default rubric for this assignment only.
              </p>
            </div>
          )}
          <div>
            <Label>File (PDF or Word)</Label>
            <div className="mt-1 upload-zone rounded-lg p-6 text-center cursor-pointer">
              <label htmlFor="material-file" className="cursor-pointer block">
                {materialForm.file ? (
                  <div className="flex items-center justify-center gap-2">
                    <File className="w-5 h-5 text-[#22438E]" />
                    <span className="text-sm text-[#000000]">{materialForm.file.name}</span>
                  </div>
                ) : (
                  <>
                    <Upload className="w-8 h-8 text-[#94B8D9] mx-auto mb-2" />
                    <p className="text-sm text-[#666666]">Click to upload PDF or DOCX</p>
                  </>
                )}
              </label>
            </div>
            <input id="material-file" data-testid="material-file-input" type="file" accept=".pdf,.docx"
              className="hidden" onChange={(e) => setMaterialForm({ ...materialForm, file: e.target.files[0] })} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="upload-material-submit" onClick={onSubmit} disabled={uploadingMaterial}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">
            {uploadingMaterial ? 'Uploading...' : 'Upload'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function SubmitHomeworkDialog({ open, onOpenChange, selectedHomework, homeworkFile, setHomeworkFile, submittingHomework, onSubmit }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Submit Homework</DialogTitle>
          <DialogDescription>{selectedHomework?.title}</DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <Label>Your Submission (PDF or Word)</Label>
          <div className="mt-1 upload-zone rounded-lg p-8 text-center cursor-pointer">
            <label htmlFor="homework-file" className="cursor-pointer block">
              {homeworkFile ? (
                <div className="flex items-center justify-center gap-2">
                  <File className="w-5 h-5 text-[#22438E]" />
                  <span className="text-sm text-[#000000]">{homeworkFile.name}</span>
                </div>
              ) : (
                <>
                  <Upload className="w-10 h-10 text-[#94B8D9] mx-auto mb-2" />
                  <p className="text-sm text-[#666666]">Click to upload your homework</p>
                  <p className="text-xs text-[#94B8D9] mt-1">PDF or DOCX only</p>
                </>
              )}
            </label>
          </div>
          <input id="homework-file" data-testid="homework-file-input" type="file" accept=".pdf,.docx"
            className="hidden" onChange={(e) => setHomeworkFile(e.target.files[0])} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="submit-homework-btn" onClick={onSubmit} disabled={submittingHomework}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">
            {submittingHomework ? 'Submitting...' : 'Submit'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function BulkImportDialog({ open, onOpenChange, bulkFile, setBulkFile, importingBulk, importResults, onSubmit, onDownloadTemplate, onClose }) {
  return (
    <Dialog open={open} onOpenChange={(val) => { onOpenChange(val); if (!val) onClose(); }}>
      <DialogContent className="bg-white max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Bulk Import Students</DialogTitle>
          <DialogDescription>Upload a CSV file with student emails. Students will be added to this cohort.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="flex items-center justify-between p-4 bg-[#D0E6F9] rounded-lg">
            <div>
              <p className="text-sm font-medium text-[#000000]">Need a template?</p>
              <p className="text-xs text-[#666666]">Download our CSV template to get started</p>
            </div>
            <Button variant="outline" size="sm" onClick={onDownloadTemplate} className="border-[#B8D4E8]">
              <Download className="w-4 h-4 mr-2" />Template
            </Button>
          </div>
          <div>
            <Label>CSV File</Label>
            <div className="mt-1 upload-zone rounded-lg p-6 text-center cursor-pointer">
              <label htmlFor="bulk-file" className="cursor-pointer block">
                {bulkFile ? (
                  <div className="flex items-center justify-center gap-2">
                    <File className="w-5 h-5 text-[#22438E]" />
                    <span className="text-sm text-[#000000]">{bulkFile.name}</span>
                  </div>
                ) : (
                  <>
                    <FileUp className="w-8 h-8 text-[#94B8D9] mx-auto mb-2" />
                    <p className="text-sm text-[#666666]">Click to upload CSV file</p>
                    <p className="text-xs text-[#94B8D9] mt-1">Required column: email</p>
                  </>
                )}
              </label>
            </div>
            <input id="bulk-file" data-testid="bulk-file-input" type="file" accept=".csv"
              className="hidden" onChange={(e) => setBulkFile(e.target.files[0])} />
          </div>
          {importResults && (
            <div className="space-y-3">
              {importResults.added?.length > 0 && (
                <div className="flex items-start gap-2 p-3 bg-[#E1F0FF] rounded-lg">
                  <CheckCircle className="w-4 h-4 text-[#22438E] mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-[#22438E]">{importResults.added.length} students added</p>
                    <p className="text-xs text-[#22438E]">{importResults.added.map(s => s.name || s.email).join(', ')}</p>
                  </div>
                </div>
              )}
              {importResults.already_enrolled?.length > 0 && (
                <div className="flex items-start gap-2 p-3 bg-[#FEF9C3] rounded-lg">
                  <AlertCircle className="w-4 h-4 text-[#1A75BA] mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-[#1A75BA]">{importResults.already_enrolled.length} already enrolled</p>
                    <p className="text-xs text-[#1A75BA]">{importResults.already_enrolled.join(', ')}</p>
                  </div>
                </div>
              )}
              {importResults.not_found?.length > 0 && (
                <div className="flex items-start gap-2 p-3 bg-[#FEE2E2] rounded-lg">
                  <AlertCircle className="w-4 h-4 text-red-600 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-red-600">{importResults.not_found.length} not found</p>
                    <p className="text-xs text-red-600">{importResults.not_found.join(', ')} (not registered yet)</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { onOpenChange(false); onClose(); }}>
            {importResults ? 'Close' : 'Cancel'}
          </Button>
          {!importResults && (
            <Button data-testid="bulk-import-submit" onClick={onSubmit} disabled={importingBulk || !bulkFile}
              className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">
              {importingBulk ? 'Importing...' : 'Import Students'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function InviteLinkDialog({ open, onOpenChange, cohort, copied, setCopied }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white max-w-sm">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Invite Students</DialogTitle>
          <DialogDescription>Share this link or QR code so students can join {cohort?.name}</DialogDescription>
        </DialogHeader>
        <div className="py-4 space-y-6">
          <div className="flex justify-center">
            <div className="bg-white p-4 rounded-xl border border-[#B8D4E8]">
              <QRCodeSVG value={`${window.location.origin}/invite/${cohort?.invite_code}`} size={200} level="M" data-testid="invite-qr-code" />
            </div>
          </div>
          <div>
            <Label className="text-xs text-[#666666] uppercase tracking-wide">Invite Link</Label>
            <div className="mt-1 flex items-center gap-2">
              <input readOnly value={`${window.location.origin}/invite/${cohort?.invite_code}`}
                className="flex-1 px-3 py-2 bg-[#D0E6F9] rounded-lg text-sm text-[#000000] border-0 outline-none" data-testid="invite-url-input" />
              <Button variant="outline" size="icon" className="flex-shrink-0 rounded-lg"
                onClick={() => {
                  navigator.clipboard.writeText(`${window.location.origin}/invite/${cohort?.invite_code}`);
                  setCopied(true);
                  toast.success('Link copied!');
                  setTimeout(() => setCopied(false), 2000);
                }}
                data-testid="copy-invite-link">
                {copied ? <Check className="w-4 h-4 text-[#22438E]" /> : <Copy className="w-4 h-4" />}
              </Button>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-lg">Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AssignInstructorDialog({ open, onOpenChange, cohort, instructorsList, onAssign }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Assign Instructor</DialogTitle>
          <DialogDescription>Choose an instructor to manage this cohort. They will be able to see submissions and track student progress.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-4 max-h-[400px] overflow-y-auto">
          {instructorsList.length === 0 ? (
            <p className="text-sm text-[#666666] text-center py-4">No instructors found. Promote a user to instructor first.</p>
          ) : (
            instructorsList.map((inst) => {
              const isAssigned = cohort?.instructor_ids?.includes(inst.user_id);
              return (
                <div key={inst.user_id}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    isAssigned ? 'border-[#22438E] bg-[#E1F0FF]' : 'border-[#B8D4E8] hover:bg-[#E1F0FF]'
                  }`}
                  onClick={() => onAssign(inst.user_id)}
                  data-testid={`assign-instructor-${inst.user_id}`}>
                  <div className="w-10 h-10 bg-[#D0E6F9] rounded-full flex items-center justify-center flex-shrink-0">
                    {inst.picture ? (
                      <img src={inst.picture} alt={inst.name} className="w-10 h-10 rounded-full" />
                    ) : (
                      <UserCog className="w-5 h-5 text-[#666666]" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-[#000000] truncate">{inst.name}</p>
                    <p className="text-xs text-[#666666] truncate">{inst.email}</p>
                  </div>
                  {isAssigned && (
                    <span className="text-xs bg-[#22438E] text-white px-2 py-0.5 rounded-full flex-shrink-0">Assigned</span>
                  )}
                  {inst.role === 'super_admin' && (
                    <span className="text-xs bg-[#000000] text-white px-2 py-0.5 rounded-full flex-shrink-0">Admin</span>
                  )}
                </div>
              );
            })
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-lg">Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function SubmitOnBehalfDialog({ open, onOpenChange, cohort, homeworkList, onSubmit, submitting }) {
  const [selectedStudent, setSelectedStudent] = React.useState('');
  const [selectedHomework, setSelectedHomework] = React.useState('');
  const [file, setFile] = React.useState(null);

  const students = (cohort?.students || []).filter(s => s.user_id);

  const handleSubmit = () => {
    if (!selectedStudent || !selectedHomework || !file) {
      toast.error('Please select a student, homework, and file');
      return;
    }
    onSubmit({ studentId: selectedStudent, materialId: selectedHomework, file });
  };

  const handleClose = (v) => {
    if (!v) { setSelectedStudent(''); setSelectedHomework(''); setFile(null); }
    onOpenChange(v);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="bg-white">
        <DialogHeader>
          <DialogTitle className="font-normal text-2xl">Submit on Behalf of Student</DialogTitle>
          <DialogDescription>Upload a homework file for a student in this cohort. AI feedback will be generated automatically.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label>Student *</Label>
            <Select value={selectedStudent} onValueChange={setSelectedStudent}>
              <SelectTrigger className="mt-1" data-testid="behalf-student-select">
                <SelectValue placeholder="Select a student" />
              </SelectTrigger>
              <SelectContent>
                {students.map(s => (
                  <SelectItem key={s.user_id} value={s.user_id}>{s.name || s.email}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Homework Assignment *</Label>
            <Select value={selectedHomework} onValueChange={setSelectedHomework}>
              <SelectTrigger className="mt-1" data-testid="behalf-homework-select">
                <SelectValue placeholder="Select homework" />
              </SelectTrigger>
              <SelectContent>
                {homeworkList.map(hw => (
                  <SelectItem key={hw.material_id} value={hw.material_id}>
                    Week {hw.week_number} — {hw.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>File (PDF or DOCX) *</Label>
            <div className="mt-1 upload-zone rounded-lg p-6 text-center cursor-pointer">
              <label htmlFor="behalf-file" className="cursor-pointer block">
                {file ? (
                  <div className="flex items-center justify-center gap-2">
                    <File className="w-5 h-5 text-[#22438E]" />
                    <span className="text-sm text-[#000000]">{file.name}</span>
                  </div>
                ) : (
                  <>
                    <Upload className="w-8 h-8 text-[#94B8D9] mx-auto mb-2" />
                    <p className="text-sm text-[#666666]">Click to upload</p>
                    <p className="text-xs text-[#94B8D9] mt-1">PDF or DOCX</p>
                  </>
                )}
              </label>
            </div>
            <input id="behalf-file" data-testid="behalf-file-input" type="file" accept=".pdf,.docx"
              className="hidden" onChange={(e) => setFile(e.target.files[0])} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>Cancel</Button>
          <Button data-testid="submit-on-behalf-btn" onClick={handleSubmit} disabled={submitting}
            className="bg-[#22438E] text-white hover:bg-[#1A3A7A]">
            {submitting ? 'Submitting...' : 'Submit on Behalf'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

