/**
 * Inline modal editor for route metadata (title, description, notes).
 * showMetadataEditor(route, onSave)
 */

export function showMetadataEditor(route, onSave) {
  const overlay = document.getElementById('metadata-modal-overlay');
  overlay.innerHTML = '';
  overlay.classList.add('visible');

  const box = document.createElement('div');
  box.className = 'confirm-box metadata-editor';

  box.innerHTML = `
    <h3 class="modal-title">Edit Route</h3>
    <div class="form-group">
      <label>Title <span class="required">*</span></label>
      <input type="text" class="tag-input edit-title" />
      <span class="validation-error" style="display:none">Title is required</span>
    </div>
    <div class="form-group">
      <label>Description</label>
      <textarea class="tag-input edit-desc" rows="3"></textarea>
    </div>
    <div class="form-group">
      <label>Notes</label>
      <textarea class="tag-input edit-notes" rows="3"></textarea>
    </div>
    <div class="confirm-actions">
      <button class="btn btn-secondary cancel-edit">Cancel</button>
      <button class="btn btn-primary save-edit">Save</button>
    </div>
  `;

  overlay.appendChild(box);

  const titleInput = box.querySelector('.edit-title');
  const descInput = box.querySelector('.edit-desc');
  const notesInput = box.querySelector('.edit-notes');
  const validErr = box.querySelector('.validation-error');

  titleInput.value = route.title || '';
  descInput.value = route.description || '';
  notesInput.value = route.notes || '';
  titleInput.focus();

  function close() {
    overlay.classList.remove('visible');
    overlay.innerHTML = '';
  }

  box.querySelector('.cancel-edit').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  box.querySelector('.save-edit').addEventListener('click', () => {
    const title = titleInput.value.trim();
    if (!title) {
      validErr.style.display = '';
      titleInput.focus();
      return;
    }
    onSave({
      title,
      description: descInput.value.trim(),
      notes: notesInput.value.trim(),
    });
    close();
  });

  titleInput.addEventListener('input', () => { validErr.style.display = 'none'; });
}
