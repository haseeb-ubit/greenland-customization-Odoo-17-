(function () {
    // Capture-phase listener so we run before Odoo intercepts the click
    document.addEventListener('click', function (ev) {
        var btn = ev.target && ev.target.closest("button[name='action_copy_link']");
        if (!btn) {
            return;
        }
        // Try to copy immediately
        var root = btn.closest('.o_dialog, .modal, .o_modal');
        var node = root ? root.querySelector("[name='link']") : document.querySelector("[name='link']");
        var text = node ? (node.value || node.textContent || node.innerText || '') : '';
        if (!text) {
            return;
        }
        var fallbackCopy = function () {
            try {
                var ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.top = '-1000px';
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
            } catch (e) {}
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).catch(fallbackCopy);
        } else {
            fallbackCopy();
        }
    }, true);
})();

