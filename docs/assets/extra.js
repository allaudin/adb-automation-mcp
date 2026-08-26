// Material for MkDocs renders each mermaid diagram into a CLOSED shadow root
// (verified against its bundled JS: `r.attachShadow({mode:"closed"})`), so the
// SVG is unreachable from page-level CSS/JS by design — including this
// script, unless shadow roots are forced open first. This patch must run
// before Material's async mermaid render actually calls attachShadow(); since
// it patches the prototype method itself (not a one-time DOM query), it's
// safe regardless of <script> tag order relative to Material's own bundle.
(function () {
  var original = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function (init) {
    return original.call(this, Object.assign({}, init, { mode: "open" }));
  };
})();

// Click-to-zoom: opens a fullscreen overlay with the diagram at its natural
// size. The diagram's own <div class="mermaid"> only gets inserted into the
// page once its shadow root is already populated (Material populates the
// shadow root, then replaces the placeholder <pre> with the div), so a single
// MutationObserver on document.body is enough to catch it.
(function () {
  function svgFor(mermaidDiv) {
    return mermaidDiv.shadowRoot ? mermaidDiv.shadowRoot.querySelector("svg") : null;
  }

  function openOverlay(svg) {
    var overlay = document.createElement("div");
    overlay.className = "mermaid-zoom-overlay";
    overlay.appendChild(svg.cloneNode(true));

    function close() {
      overlay.remove();
      document.removeEventListener("keydown", onKeydown);
    }
    function onKeydown(event) {
      if (event.key === "Escape") close();
    }

    overlay.addEventListener("click", close);
    document.addEventListener("keydown", onKeydown);
    document.body.appendChild(overlay);
  }

  function bind(div) {
    if (div.dataset.zoomBound) return;
    var svg = svgFor(div);
    if (!svg) return; // not rendered yet — next scan will retry
    div.dataset.zoomBound = "true";
    svg.style.maxWidth = "none";
    div.addEventListener("click", function () {
      var current = svgFor(div);
      if (current) openOverlay(current);
    });
  }

  function scan() {
    document.querySelectorAll(".mermaid").forEach(bind);
  }

  scan();
  new MutationObserver(scan).observe(document.body, {
    childList: true,
    subtree: true,
  });
})();
