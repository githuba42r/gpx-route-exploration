/**
 * Category sidebar panel.
 * renderCategoryPanel(container, categories, handlers)
 */

export function renderCategoryPanel(container, categories, handlers) {
  container.innerHTML = '';

  const heading = document.createElement('h3');
  heading.className = 'panel-heading';
  heading.textContent = 'Categories';
  container.appendChild(heading);

  const list = document.createElement('ul');
  list.className = 'category-list';

  categories.forEach((cat) => {
    const li = document.createElement('li');
    li.className = 'category-item';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'category-name';
    nameSpan.textContent = `${cat.name} (${cat.route_count})`;

    // Click-to-edit for non-default categories
    if (cat.slug !== 'default') {
      nameSpan.title = 'Click to rename';
      nameSpan.addEventListener('dblclick', () => {
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'tag-input';
        input.value = cat.name;
        nameSpan.replaceWith(input);
        input.focus();
        input.select();

        function commit() {
          const newName = input.value.trim();
          if (newName && newName !== cat.name) {
            handlers.onRename(cat.id, newName, cat.description);
          } else {
            input.replaceWith(nameSpan);
          }
        }

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') { e.preventDefault(); commit(); }
          if (e.key === 'Escape') input.replaceWith(nameSpan);
        });
      });

      const delBtn = document.createElement('button');
      delBtn.className = 'btn btn-sm btn-danger';
      delBtn.textContent = '\u00d7';
      delBtn.title = 'Delete category';
      delBtn.addEventListener('click', () => handlers.onDelete(cat.id));
      li.appendChild(delBtn);
    }

    li.prepend(nameSpan);
    list.appendChild(li);
  });

  container.appendChild(list);

  // Create new category form
  const form = document.createElement('div');
  form.className = 'new-category-form';

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'tag-input';
  input.placeholder = 'New category...';

  const addBtn = document.createElement('button');
  addBtn.className = 'btn btn-sm btn-primary';
  addBtn.textContent = '+ Add';

  addBtn.addEventListener('click', () => {
    const name = input.value.trim();
    if (name) {
      handlers.onCreate(name, '');
      input.value = '';
    }
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addBtn.click();
    }
  });

  form.appendChild(input);
  form.appendChild(addBtn);
  container.appendChild(form);
}
