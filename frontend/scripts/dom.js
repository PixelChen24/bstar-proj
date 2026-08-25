// Shared DOM helpers. Kept global so every feature script can stay framework-free.
window.$ = (selector, root = document) => root.querySelector(selector);
window.$$ = (selector, root = document) => [...root.querySelectorAll(selector)];
