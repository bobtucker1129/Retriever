(function() {
    "use strict";

    var DEBOUNCE_MS = 2000;
    var _lastScanValue = "";
    var _lastScanTime = 0;
    var _scanBuffer = "";
    var _scanTimer = null;

    function init() {
        var scanInput = document.getElementById("scan-input");
        if (!scanInput) return;

        scanInput.addEventListener("keydown", onScanKeydown);
        scanInput.addEventListener("focus", function() { scanInput.select(); });

        keepFocus(scanInput);
    }

    function onScanKeydown(e) {
        if (e.key !== "Enter") {
            clearTimeout(_scanTimer);
            _scanTimer = setTimeout(function() { _scanBuffer = ""; }, 300);
            return;
        }

        e.preventDefault();
        var value = e.target.value.trim();
        if (!value) return;

        var now = Date.now();
        if (value === _lastScanValue && (now - _lastScanTime) < DEBOUNCE_MS) {
            return;
        }
        _lastScanValue = value;
        _lastScanTime = now;

        htmx.trigger(document.getElementById("scan-form"), "submit");
    }

    function keepFocus(input) {
        document.addEventListener("htmx:afterSettle", function() {
            var qty = document.getElementById("quantity");
            if (qty) {
                qty.focus();
                return;
            }
            if (document.activeElement === document.body ||
                document.activeElement === document.documentElement) {
                input.focus();
            }
        });
    }

    window.invSetMode = function(mode) {
        var modeInput = document.getElementById("action-mode");
        var labelText = document.getElementById("action-label-text");
        var btnPull = document.getElementById("btn-mode-pull");
        var btnAdd = document.getElementById("btn-mode-add");

        if (!modeInput) return;

        modeInput.value = mode;
        if (labelText) labelText.textContent = mode === "pull" ? "Pull" : "Add";

        if (btnPull && btnAdd) {
            if (mode === "pull") {
                btnPull.className = "btn btn-sm btn-confirm";
                btnAdd.className = "btn btn-sm btn-secondary";
            } else {
                btnPull.className = "btn btn-sm btn-secondary";
                btnAdd.className = "btn btn-sm btn-confirm";
            }
        }
    };

    function initCountAutoFocus() {
        document.addEventListener("htmx:afterSettle", function() {
            var inputs = document.querySelectorAll(".inventory-count-qty-input");
            for (var i = 0; i < inputs.length; i++) {
                if (inputs[i].value === "") {
                    inputs[i].focus();
                    return;
                }
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function() { init(); initCountAutoFocus(); });
    } else {
        init();
        initCountAutoFocus();
    }
})();
