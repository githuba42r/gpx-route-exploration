/**
 * Tag cloud renderer with sized chips.
 * renderTagCloud(container, tags, onTagClick, activeTag)
 */

export function renderTagCloud(container, tags, onTagClick, activeTag) {
  container.innerHTML = '';
  if (!tags.length) return;

  const heading = document.createElement('h3');
  heading.className = 'panel-heading';
  heading.textContent = 'Tags';
  container.appendChild(heading);

  const cloud = document.createElement('div');
  cloud.className = 'tag-cloud';

  const maxCount = Math.max(...tags.map((t) => t.usage_count), 1);

  tags.forEach((tag) => {
    const chip = document.createElement('span');
    chip.className = 'tag-chip';
    if (tag.name === activeTag) chip.classList.add('active');

    // Scale font from 0.7em to 1.1em based on usage
    const scale = 0.7 + (tag.usage_count / maxCount) * 0.4;
    chip.style.fontSize = `${scale}em`;
    chip.textContent = `${tag.name} (${tag.usage_count})`;

    chip.addEventListener('click', () => {
      onTagClick(tag.name === activeTag ? null : tag.name);
    });

    cloud.appendChild(chip);
  });

  container.appendChild(cloud);
}
