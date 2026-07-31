// Central config for the 4 named homework submission types.
// Keep IDs in sync with /app/backend/server.py -> SUBMISSION_TYPES.

export const SUBMISSION_TYPES = [
  {
    id: '60_second_pitch',
    label: '60 Second Pitch',
    shortLabel: 'Pitch',
    description: 'Short elevator pitch — video/audio recording or written writeup.',
    accept: 'video/*,audio/*,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,.mp4,.mov,.m4v,.webm,.mp3,.m4a,.wav,.pdf,.doc,.docx,.txt',
    extensions: ['mp4', 'mov', 'm4v', 'webm', 'mp3', 'm4a', 'wav', 'pdf', 'doc', 'docx', 'txt'],
    inputKind: 'file',
    icon: 'Mic',
  },
  {
    id: '10_slide_pitch',
    label: '10 Slide Pitch Deck',
    shortLabel: 'Pitch Deck',
    description: 'Investor-style pitch deck. PDF, PowerPoint, or Word writeup.',
    accept: 'application/pdf,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.pdf,.ppt,.pptx,.doc,.docx',
    extensions: ['pdf', 'ppt', 'pptx', 'doc', 'docx'],
    inputKind: 'file',
    icon: 'Presentation',
  },
  {
    id: 'case_activity',
    label: 'The Case Activity',
    shortLabel: 'Case',
    description: 'Written case-study response or spreadsheet template. PDF, Word, plain text, or Excel/CSV.',
    accept: 'application/pdf,.pdf,application/msword,.doc,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx,text/plain,.txt,.md,.rtf,application/vnd.ms-excel,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xlsx,text/csv,.csv',
    extensions: ['pdf', 'doc', 'docx', 'txt', 'md', 'rtf', 'xlsx', 'xls', 'csv'],
    inputKind: 'file',
    icon: 'FileText',
  },
  {
    id: 'spreadsheet_analysis',
    label: 'Spreadsheet / Template',
    shortLabel: 'Sheet',
    description: 'Excel workbook, CSV, or a Google Sheets template downloaded as .xlsx. Coach Max reads the cells and references specific tabs and rows in feedback.',
    accept: 'application/vnd.ms-excel,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xlsx,text/csv,.csv',
    extensions: ['xlsx', 'xls', 'csv'],
    inputKind: 'file',
    icon: 'FileText',
  },
  {
    id: 'business_questionnaire',
    label: 'Your Business Questionnaire',
    shortLabel: 'Questionnaire',
    description: 'Structured questionnaire — students answer instructor-defined questions.',
    accept: null,
    extensions: [],
    inputKind: 'form',
    icon: 'ListChecks',
  },
];

export const SUBMISSION_TYPE_BY_ID = Object.fromEntries(
  SUBMISSION_TYPES.map((t) => [t.id, t])
);

export const SUBMISSION_TYPE_IDS = SUBMISSION_TYPES.map((t) => t.id);

/** Resolve config safely; falls back to null (generic homework) */
export function getSubmissionTypeConfig(id) {
  if (!id) return null;
  return SUBMISSION_TYPE_BY_ID[id] || null;
}
