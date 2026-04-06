import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export const downloadFile = async (url, filename) => {
  const token = localStorage.getItem('thinkific_session_token');
  if (!token) {
    toast.error('Please log in to download files');
    return;
  }
  const separator = url.includes('?') ? '&' : '?';
  try {
    const response = await fetch(`${url}${separator}token=${encodeURIComponent(token)}`);
    if (!response.ok) {
      let errorMsg = 'Download failed';
      try {
        const data = await response.json();
        errorMsg = data.detail || errorMsg;
      } catch (_) {
        errorMsg = response.status === 404 ? 'File not found on server' : `Download failed (${response.status})`;
      }
      toast.error(errorMsg);
      return;
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
  } catch (_err) {
    toast.error('Network error — unable to download file');
  }
};

export const handleDownloadMaterial = async (materialId, fileName) => {
  await downloadFile(`${API_URL}/api/materials/${materialId}/download`, fileName || 'material');
};

export const handleDownloadSubmission = async (submissionId, fileName) => {
  await downloadFile(`${API_URL}/api/submissions/${submissionId}/download`, fileName || 'submission');
};
