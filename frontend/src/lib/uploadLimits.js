// Centralised upload-size guard. Ingress / CDN proxies (including Cloudflare
// Free plan) typically reject request bodies larger than ~100 MB before they
// reach FastAPI, so the backend never gets to return a helpful error. Every
// student-facing and instructor-facing upload widget uses this to warn and
// block early.

export const MAX_UPLOAD_MB = 100;
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

export function isFileTooLarge(file) {
  return !!file && typeof file.size === 'number' && file.size > MAX_UPLOAD_BYTES;
}

export function fileSizeMbLabel(file) {
  if (!file || typeof file.size !== 'number') return '';
  return (file.size / 1024 / 1024).toFixed(0);
}

// Standard toast/dialog copy so every surface uses the same wording.
export function tooLargeMessage(file) {
  return (
    `This file is ${fileSizeMbLabel(file)} MB — over our ${MAX_UPLOAD_MB} MB upload cap. `
    + `Please compress your video (QuickTime → Export → 480p, HandBrake "Web" preset, `
    + `or the "Compress" share option on iPhone) and re-select it before submitting.`
  );
}

// Uniform error interpretation for axios upload failures so students see the
// real reason (413, timeout, network) instead of a generic "Failed to submit".
export function humanUploadError(err, fallback = 'Upload failed') {
  const detail = err?.response?.data?.detail;
  const status = err?.response?.status;
  if (detail) return detail;
  if (status === 413) {
    return `Upload rejected — file is too large for our upload proxy (over ${MAX_UPLOAD_MB} MB). Please compress it and retry.`;
  }
  if (err?.code === 'ECONNABORTED' || /timeout/i.test(err?.message || '')) {
    return `Upload timed out. This usually means the file is too large for the network — please compress it and retry.`;
  }
  if (!err?.response) {
    return `${fallback} (network / proxy error). Likely the file exceeds the ${MAX_UPLOAD_MB} MB upload cap — please compress and retry.`;
  }
  return `${fallback}${status ? ` (HTTP ${status})` : ''}`;
}
