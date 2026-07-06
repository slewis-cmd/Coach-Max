// Central config for the 4 named homework submission types.
// Keep IDs in sync with /app/backend/server.py -> SUBMISSION_TYPES.

export const SUBMISSION_TYPES = [
  {
    id: '60_second_pitch',
    label: '60 Second Pitch',
    shortLabel: 'Pitch',
    description: 'Short elevator pitch — upload a 30-90s video or audio clip.',
    accept: 'video/*,audio/*,.mp4,.mov,.m4v,.mp3,.m4a,.wav',
    extensions: ['mp4', 'mov', 'm4v', 'mp3', 'm4a', 'wav'],
    inputKind: 'file',
    icon: 'Mic',
  },
  {
    id: '10_slide_pitch',
    label: '10 Slide Pitch Deck',
    shortLabel: 'Pitch Deck',
    description: 'Investor-style pitch deck. PDF or PowerPoint.',
    accept: 'application/pdf,.pdf,application/vnd.ms-powerpoint,.ppt,application/vnd.openxmlformats-officedocument.presentationml.presentation,.pptx',
    extensions: ['pdf', 'ppt', 'pptx'],
    inputKind: 'file',
    icon: 'Presentation',
  },
  {
    id: 'case_activity',
    label: 'The Case Activity',
    shortLabel: 'Case',
    description: 'Written case-study response. PDF, DOCX or plain text.',
    accept: 'application/pdf,.pdf,application/msword,.doc,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx,text/plain,.txt',
    extensions: ['pdf', 'doc', 'docx', 'txt'],
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
