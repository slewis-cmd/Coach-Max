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
    toast.error('Failed to download file');
  }
};

export const handleDownloadMaterial = async (materialId, fileName) => {
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
    toast.error('Failed to download file');
  }
};
