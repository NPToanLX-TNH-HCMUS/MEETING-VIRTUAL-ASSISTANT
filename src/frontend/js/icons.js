// Line icons, drawn as SVG paths (24x24, stroke only). Built with createElementNS, never innerHTML.
const NS = 'http://www.w3.org/2000/svg';

const ICONS = {
  // app chrome
  plus: ['M12 5v14', 'M5 12h14'],
  home: ['M3 11l9-8 9 8', 'M5 10v10h14V10'],
  live: ['M4 10v4', 'M8 7v10', 'M12 4v16', 'M16 8v8', 'M20 11v2'],
  review: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M14 3v5h5', 'M9 13h6', 'M9 17h4'],
  sidebar: ['M3 6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', 'M9 4v16'],
  back: ['M15 6l-6 6 6 6'],
  forward: ['M9 6l6 6-6 6'],
  settings: ['M4 7h9', 'M17 7h3', 'M4 17h3', 'M11 17h9', 'M15 5a2 2 0 1 0 0 4a2 2 0 1 0 0-4z', 'M9 15a2 2 0 1 0 0 4a2 2 0 1 0 0-4z'],
  chevron: ['M9 6l6 6-6 6'],
  edit: ['M4 20h4l10.5-10.5a2.1 2.1 0 0 0-4-4L4 16z', 'M13.5 6.5l4 4'],
  // the ones a workspace can use
  folder: ['M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'],
  calendar: ['M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z', 'M4 11h16', 'M8 3v4', 'M16 3v4'],
  briefcase: ['M4 8h16a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z', 'M9 8V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2', 'M3 13h18'],
  heart: ['M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z'],
  star: ['M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z'],
  target: ['M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z', 'M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8z'],
  bolt: ['M13 3L5 13h6l-1 8 8-10h-6z'],
  book: ['M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z', 'M5 17a3 3 0 0 1 3-3h10'],
  flag: ['M5 21V4', 'M5 4h12l-2 4 2 4H5'],
  chat: ['M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z'],
  users: ['M9 11a3 3 0 1 0 0-6a3 3 0 1 0 0 6z', 'M3 19a6 6 0 0 1 12 0', 'M16 5.3a3 3 0 0 1 0 5.4', 'M17 14a6 6 0 0 1 4 5'],
  bulb: ['M9 18h6', 'M10 21h4', 'M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z'],
};

// What the "new workspace" window offers. The backend stores only the names.
export const WORKSPACE_ICONS = ['folder', 'calendar', 'briefcase', 'heart', 'star', 'target', 'bolt', 'book', 'flag', 'chat', 'users', 'bulb'];
export const WORKSPACE_COLORS = ['violet', 'teal', 'green', 'amber', 'red', 'blue', 'pink'];

export function icon(name, size = 18) {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  for (const d of ICONS[name] ?? ICONS.folder) {
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', d);
    svg.append(path);
  }
  return svg;
}

// A name from the backend that this UI does not know still gets a usable icon and colour.
export const workspaceIcon = (name) => (WORKSPACE_ICONS.includes(name) ? name : 'folder');
export const workspaceColor = (name) => (WORKSPACE_COLORS.includes(name) ? name : 'violet');
