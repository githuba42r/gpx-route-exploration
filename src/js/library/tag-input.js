/**
 * Tag chip input with auto-complete.
 * createTagInput(container, existingTags, onChange)
 */

export function createTagInput(container, existingTags, onChange) {
  let selected = [];
  container.innerHTML = '';
  container.classList.add('tag-input-wrapper');

  const chipsEl = document.createElement('div');
  chipsEl.className = 'tag-chips';
  container.appendChild(chipsEl);

  const inputWrap = document.createElement('div');
  inputWrap.style.position = 'relative';
  container.appendChild(inputWrap);

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'tag-input';
  input.placeholder = 'Add tag...';
  inputWrap.appendChild(input);

  const sugBox = document.createElement('div');
  sugBox.className = 'tag-suggestions';
  sugBox.style.display = 'none';
  inputWrap.appendChild(sugBox);

  function render() {
    chipsEl.innerHTML = '';
    selected.forEach((tag) => {
      const chip = document.createElement('span');
      chip.className = 'tag-chip';
      chip.textContent = tag;
      const rm = document.createElement('span');
      rm.className = 'tag-remove';
      rm.textContent = '\u00d7';
      rm.addEventListener('click', () => {
        selected = selected.filter((t) => t !== tag);
        render();
        onChange(selected);
      });
      chip.appendChild(rm);
      chipsEl.appendChild(chip);
    });
  }

  function showSuggestions(query) {
    const q = query.toLowerCase();
    const matches = existingTags.filter(
      (t) => t.toLowerCase().includes(q) && !selected.includes(t)
    );
    if (!matches.length || !q) {
      sugBox.style.display = 'none';
      return;
    }
    sugBox.innerHTML = '';
    sugBox.style.display = '';
    matches.slice(0, 8).forEach((name) => {
      const div = document.createElement('div');
      div.className = 'suggestion';
      div.textContent = name;
      div.addEventListener('mousedown', (e) => {
        e.preventDefault();
        addTag(name);
      });
      sugBox.appendChild(div);
    });
  }

  function addTag(name) {
    const trimmed = name.trim();
    if (!trimmed || selected.includes(trimmed)) return;
    selected.push(trimmed);
    input.value = '';
    sugBox.style.display = 'none';
    render();
    onChange(selected);
  }

  input.addEventListener('input', () => showSuggestions(input.value));
  input.addEventListener('blur', () => { sugBox.style.display = 'none'; });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addTag(input.value);
    }
  });

  // Public API to set initial selection
  return {
    setTags(tags) {
      selected = [...tags];
      render();
    },
    getTags() {
      return [...selected];
    },
  };
}
