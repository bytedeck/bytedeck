/*
 * Draws each formula the editor's Insert Math button inserted again, from the LaTeX it keeps.
 *
 * summernote-math.js stores a formula as the HTML KaTeX built when it was typed (span.note-math),
 * followed by the LaTeX it was built from in a hidden span.note-latex. That HTML only lays out
 * under the stylesheet of the KaTeX version that built it: KaTeX renames the classes its layout
 * hangs on between versions, so content written under an older version than the page loads comes
 * out with its parts out of place, an accent's arrow under the letter and a fraction overlapping
 * itself (#2884). Rendering each formula again from its LaTeX with the page's own KaTeX keeps the
 * markup and the stylesheet the same version, whenever the formula was written.
 *
 * The page's formulas are drawn once it has loaded, and any added to it later as they arrive: the
 * quest list's previews load by AJAX, and an editor fills itself with the text it opens with after
 * the page has loaded. A formula drawn in an editor is saved drawn by this version when the text is.
 */
(function () {
    "use strict";

    // the formulas already drawn here, so a formula moved around the page isn't drawn again
    var drawn = new WeakSet();

    /**
     * Replaces a formula's stored rendering with KaTeX's rendering of its LaTeX.
     *
     * A formula with no LaTeX beside it, or LaTeX this KaTeX can't parse, keeps the rendering it
     * was stored with, since that is still the closest thing to what its author saw.
     *
     * @param {Element} math - a span.note-math.
     */
    function drawFormula(math) {
        drawn.add(math);
        var latex = math.querySelector(":scope > .note-latex");
        if (!latex) {
            return;
        }
        var rendering = document.createElement("span");
        try {
            katex.render(latex.textContent, rendering);
        } catch (e) {
            return;
        }
        Array.from(math.childNodes).forEach(function (node) {
            if (node !== latex) {
                math.removeChild(node);
            }
        });
        while (rendering.firstChild) {
            math.insertBefore(rendering.firstChild, latex);
        }
    }

    /**
     * Draws the formulas inside root (root itself included) that haven't been drawn yet.
     *
     * @param {Document|Element} root - where to look.
     */
    function drawFormulasIn(root) {
        var formulas = Array.from(root.querySelectorAll(".note-math"));
        if (root.matches && root.matches(".note-math")) {
            formulas.unshift(root);
        }
        formulas.forEach(function (math) {
            if (!drawn.has(math)) {
                drawFormula(math);
            }
        });
    }

    /**
     * Draws the page's formulas, then watches for formulas added to it later.
     */
    function start() {
        if (typeof katex === "undefined") {
            return;
        }
        drawFormulasIn(document);
        new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        drawFormulasIn(node);
                    }
                });
            });
        }).observe(document.body, {childList: true, subtree: true});
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
