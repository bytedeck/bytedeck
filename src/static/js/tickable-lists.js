/*
 * Tick boxes on quest lists (#1074).
 *
 * A long list of steps is easy to lose your place in, so in a quest's Quest Details and Submission
 * Instructions (the elements marked .tickable-scope) each item of a list with the "tickable" class
 * gets a tick box: in place of the bullet on a bulleted list, beside the number on a numbered one.
 * A scope marked data-tickable-all (the deck's tickable_lists option) makes every list in it
 * tickable. The ticks aren't saved: they last until the page is reloaded.
 */
(function () {
  'use strict';

  /**
   * The first child of `item` that holds something, skipping the whitespace between tags.
   *
   * @param {Element} item - a list item.
   * @returns {Node|null} the item's first non-blank child node.
   */
  function firstContent(item) {
    var node = item.firstChild;
    while (node && node.nodeType === Node.TEXT_NODE && !node.textContent.trim()) {
      node = node.nextSibling;
    }
    return node;
  }

  /**
   * Put a tick box at the start of each item of every tickable list in `scope`.
   *
   * An item whose text sits in a paragraph gets its box inside that paragraph, so the box stays on
   * the text's line. An item that already has its box is left alone.
   *
   * @param {Element} scope - a .tickable-scope element.
   */
  function addTickBoxes(scope) {
    if (scope.hasAttribute('data-tickable-all')) {
      scope.querySelectorAll('ul, ol').forEach(function (list) {
        list.classList.add('tickable');
      });
    }
    scope.querySelectorAll('ul.tickable > li, ol.tickable > li').forEach(function (item) {
      var first = firstContent(item);
      var target = first && first.nodeType === Node.ELEMENT_NODE && first.tagName === 'P' ? first : item;
      if (target.querySelector(':scope > .tickable-box')) {
        return;
      }
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.className = 'tickable-box';
      box.setAttribute('aria-label', 'Done');
      target.insertBefore(box, target.firstChild);
    });
  }

  function init() {
    document.querySelectorAll('.tickable-scope').forEach(addTickBoxes);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
