import React from 'react';
import { Download } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';

function PreviewBody({ mat, previewText, apiUrl }) {
  const ext = (mat.file_name || '').toLowerCase().split('.').pop();
  const token = localStorage.getItem('thinkific_session_token');

  if (mat.material_type === 'video') {
    const url = mat.video_url || '';
    const ytMatch = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([\w-]{6,})/);
    if (ytMatch) {
      return (
        <iframe
          title="Video preview"
          src={`https://www.youtube.com/embed/${ytMatch[1]}`}
          className="w-full h-[75vh] rounded-md border border-[#B8D4E8]"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          data-testid="library-preview-youtube"
        />
      );
    }
    const vmMatch = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
    if (vmMatch) {
      return (
        <iframe
          title="Video preview"
          src={`https://player.vimeo.com/video/${vmMatch[1]}`}
          className="w-full h-[75vh] rounded-md border border-[#B8D4E8]"
          allow="autoplay; fullscreen; picture-in-picture"
          allowFullScreen
          data-testid="library-preview-vimeo"
        />
      );
    }
    if (url) {
      return (
        <div className="p-8 text-center border border-[#B8D4E8] rounded-md">
          <a href={url} target="_blank" rel="noreferrer" className="text-[#22438E] underline break-all">
            {url}
          </a>
        </div>
      );
    }
    const src = `${apiUrl}/api/materials/${mat.material_id}/download?inline=1&token=${encodeURIComponent(token || '')}`;
    return (
      <video
        src={src}
        controls
        className="w-full h-[75vh] rounded-md border border-[#B8D4E8] bg-black"
        data-testid="library-preview-video"
      />
    );
  }
  if (ext === 'pdf') {
    const src = `${apiUrl}/api/materials/${mat.material_id}/download?inline=1&token=${encodeURIComponent(token || '')}`;
    return (
      <iframe
        title="Material preview"
        src={src}
        className="w-full h-[75vh] rounded-md border border-[#B8D4E8]"
        data-testid="library-preview-pdf"
      />
    );
  }
  return (
    <pre
      className="whitespace-pre-wrap text-sm text-[#1A1A1A] font-sans leading-relaxed max-h-[75vh] overflow-auto border border-[#B8D4E8] rounded-md p-4 bg-[#FAFAFA]"
      data-testid="library-preview-docx"
    >
      {previewText || 'No extractable text in this file.'}
    </pre>
  );
}

export function LibraryPreviewDialog({
  previewMat,
  previewText,
  onClose,
  apiUrl,
  downloadFile,
}) {
  return (
    <Dialog open={!!previewMat} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="bg-white max-w-5xl w-[95vw] p-0" data-testid="library-preview-dialog">
        <DialogHeader className="px-6 pt-6 pb-3 border-b border-[#B8D4E8]">
          <DialogTitle className="font-normal text-xl flex items-center justify-between gap-4">
            <span className="truncate">{previewMat?.title || 'Preview'}</span>
            {!(previewMat?.material_type === 'video' && previewMat?.video_url) && (
              <button
                onClick={() => downloadFile(`${apiUrl}/api/materials/${previewMat?.material_id}/download`, previewMat?.file_name)}
                className="inline-flex items-center gap-1.5 text-sm text-[#22438E] hover:bg-[#E1F0FF] px-3 py-1.5 rounded-md font-normal"
                data-testid="preview-download-btn"
              >
                <Download className="w-4 h-4" />
                Download
              </button>
            )}
          </DialogTitle>
          <DialogDescription className="text-xs">
            {previewMat?.material_type === 'video' && previewMat?.video_url
              ? previewMat.video_url
              : `${previewMat?.file_name || ''} · Week ${previewMat?.week_number || ''}`}
          </DialogDescription>
        </DialogHeader>
        <div className="px-6 pb-6 pt-2">
          {previewMat && <PreviewBody mat={previewMat} previewText={previewText} apiUrl={apiUrl} />}
        </div>
      </DialogContent>
    </Dialog>
  );
}
