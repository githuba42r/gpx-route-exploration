/**
 * Upload area with drag-and-drop and form.
 * initUpload(container, categories, onUploaded)
 */

import { api } from './api-client.js';

export function initUpload(container, categories, onUploaded) {
  container.innerHTML = '';

  // Drop zone
  const zone = document.createElement('div');
  zone.className = 'upload-zone';
  zone.innerHTML = '<p>Drop GPX file here or <span class="upload-browse">browse</span></p>';

  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.gpx';
  fileInput.style.display = 'none';
  container.appendChild(fileInput);

  zone.querySelector('.upload-browse').addEventListener('click', () => fileInput.click());

  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) showForm(file);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) showForm(fileInput.files[0]);
  });

  container.appendChild(zone);

  // Form (hidden until file selected)
  const formEl = document.createElement('div');
  formEl.className = 'upload-form';
  formEl.style.display = 'none';
  container.appendChild(formEl);

  function showForm(file) {
    zone.style.display = 'none';
    formEl.style.display = '';
    formEl.innerHTML = '';

    const titleFromFile = file.name.replace(/\.gpx$/i, '');

    formEl.innerHTML = `
      <div class="form-group">
        <label>Title <span class="required">*</span></label>
        <input type="text" class="tag-input upload-title" value="${titleFromFile}" />
        <span class="validation-error" style="display:none">Title is required</span>
      </div>
      <div class="form-group">
        <label>Category</label>
        <select class="upload-category tag-input">
          ${categories.map((c) => `<option value="${c.id}">${c.name}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label>Description</label>
        <textarea class="tag-input upload-desc" rows="2"></textarea>
      </div>
      <div class="form-group">
        <label>Notes</label>
        <textarea class="tag-input upload-notes" rows="2"></textarea>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary upload-submit">Upload</button>
        <button class="btn btn-secondary upload-cancel">Cancel</button>
      </div>
      <div class="upload-status"></div>
    `;

    const titleInput = formEl.querySelector('.upload-title');
    const validErr = formEl.querySelector('.validation-error');

    formEl.querySelector('.upload-cancel').addEventListener('click', resetForm);

    formEl.querySelector('.upload-submit').addEventListener('click', async () => {
      const title = titleInput.value.trim();
      if (!title) {
        validErr.style.display = '';
        titleInput.focus();
        return;
      }
      validErr.style.display = 'none';

      const status = formEl.querySelector('.upload-status');
      status.textContent = 'Uploading...';

      const fd = new FormData();
      fd.append('file', file);
      fd.append('title', title);
      fd.append('category_id', formEl.querySelector('.upload-category').value);
      fd.append('description', formEl.querySelector('.upload-desc').value.trim());
      fd.append('notes', formEl.querySelector('.upload-notes').value.trim());

      try {
        await api.uploadRoute(fd);
        status.textContent = '';
        resetForm();
        onUploaded();
      } catch (err) {
        status.textContent = `Error: ${err.message}`;
      }
    });

    titleInput.addEventListener('input', () => { validErr.style.display = 'none'; });
  }

  function resetForm() {
    formEl.style.display = 'none';
    formEl.innerHTML = '';
    zone.style.display = '';
    fileInput.value = '';
  }
}
