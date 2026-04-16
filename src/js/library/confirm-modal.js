/**
 * Inline dark-themed confirmation modal.
 * Returns a Promise<boolean> — true for confirm, false for cancel.
 */

const overlay = () => document.getElementById('confirm-modal-overlay');

export function confirmAction(message) {
  return new Promise((resolve) => {
    const el = overlay();
    el.innerHTML = '';
    el.classList.add('visible');

    const box = document.createElement('div');
    box.className = 'confirm-box';

    const msg = document.createElement('p');
    msg.className = 'confirm-message';
    msg.textContent = message;
    box.appendChild(msg);

    const actions = document.createElement('div');
    actions.className = 'confirm-actions';

    const btnConfirm = document.createElement('button');
    btnConfirm.className = 'btn btn-danger';
    btnConfirm.textContent = 'Confirm';

    const btnCancel = document.createElement('button');
    btnCancel.className = 'btn btn-secondary';
    btnCancel.textContent = 'Cancel';

    actions.appendChild(btnCancel);
    actions.appendChild(btnConfirm);
    box.appendChild(actions);
    el.appendChild(box);

    function close(result) {
      el.classList.remove('visible');
      el.innerHTML = '';
      resolve(result);
    }

    btnConfirm.addEventListener('click', () => close(true));
    btnCancel.addEventListener('click', () => close(false));
    el.addEventListener('click', (e) => {
      if (e.target === el) close(false);
    });
  });
}
