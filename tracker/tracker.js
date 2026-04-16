(function () {
  var script = document.currentScript;
  var API_KEY = script && script.getAttribute("data-key") || "";
  var ENDPOINT = script ? script.src.replace(/\/tracker\.js.*$/, "/api/event") : "/api/event";

  var STORAGE_KEY = "_trk_uid";

  function getUserId() {
    var uid = localStorage.getItem(STORAGE_KEY);
    if (uid) return uid;
    uid = "u_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(STORAGE_KEY, uid);
    return uid;
  }

  var userId = getUserId();

  function send(eventName, meta) {
    var payload = {
      apiKey: API_KEY,
      event: eventName,
      user_id: userId,
      url: location.href,
      timestamp: Date.now(),
      metadata: meta || {}
    };
    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true
    }).catch(function () {});
  }

  // page_view — on load
  send("page_view", { referrer: document.referrer, title: document.title });

  // click + add_to_cart — any button / [role=button] / input[type=submit]
  document.addEventListener("click", function (e) {
    var el = e.target.closest("button, [role='button'], input[type='submit'], a");
    if (!el) return;

    var text = (el.textContent || el.value || "").trim().toLowerCase();
    var meta = { tag: el.tagName, text: text.slice(0, 120) };

    var cartWords = ["koszyk", "cart", "add", "dodaj"];
    var isCart = cartWords.some(function (w) { return text.indexOf(w) !== -1; });

    if (isCart) {
      send("add_to_cart", meta);
    } else {
      send("click", meta);
    }
  }, true);
})();
