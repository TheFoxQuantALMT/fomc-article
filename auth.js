(function() {
  var CORRECT_HASH = 'a0a0b1c7ac7500f7e45f1b686d2427e04d59a76f3545b84569818713a1460f08';

  function sha256(message) {
    var msgBuffer = new TextEncoder().encode(message);
    return crypto.subtle.digest('SHA-256', msgBuffer).then(function(hashBuffer) {
      var hashArray = Array.from(new Uint8Array(hashBuffer));
      return hashArray.map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
    });
  }

  if (sessionStorage.getItem('fomc_auth') === 'true') return;

  document.body.style.display = 'none';

  var overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:#06090f;display:flex;align-items:center;justify-content:center;z-index:99999;font-family:Georgia,serif;';
  overlay.innerHTML = '<div style="text-align:center;color:#c8d6e5;">' +
    '<h2 style="color:#e8dcc8;margin-bottom:20px;">This page is protected</h2>' +
    '<input id="fomc-pwd" type="password" placeholder="Enter password" style="padding:10px 16px;font-size:16px;border:1px solid #c9a84c33;background:#0d1520;color:#e8dcc8;border-radius:4px;width:260px;">' +
    '<br><button id="fomc-btn" style="margin-top:12px;padding:8px 24px;background:#c9a84c;color:#06090f;border:none;border-radius:4px;cursor:pointer;font-size:14px;font-weight:600;">Enter</button>' +
    '<p id="fomc-err" style="color:#e74c3c;margin-top:12px;display:none;">Wrong password</p>' +
    '</div>';
  document.documentElement.appendChild(overlay);

  function tryAuth() {
    var pwd = document.getElementById('fomc-pwd').value;
    if (!pwd) return;
    sha256(pwd).then(function(hash) {
      if (hash === CORRECT_HASH) {
        sessionStorage.setItem('fomc_auth', 'true');
        overlay.remove();
        document.body.style.display = '';
      } else {
        document.getElementById('fomc-err').style.display = 'block';
      }
    });
  }

  overlay.querySelector('#fomc-btn').addEventListener('click', tryAuth);
  overlay.querySelector('#fomc-pwd').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') tryAuth();
  });
})();
