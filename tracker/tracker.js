(function () {
  var script = document.currentScript;
  var API_KEY = script && script.getAttribute("data-key") || "";
  var ENDPOINT = script ? script.src.replace(/\/tracker\.js.*$/, "/api/event") : "/api/event";

  var STORAGE_KEY = "_trk_uid";
<<<<<<< HEAD
=======
  var SESSION_KEY = "_trk_sid";
  var SESSION_LAST_SEEN_KEY = "_trk_sid_last_seen";
  var SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 min
>>>>>>> dev
  var VIEW_ITEM_KEY = "_trk_view_item_sent";
  var CHECKOUT_KEY = "_trk_begin_checkout_sent";
  var CHECKOUT_STEP_PREFIX = "_trk_checkout_step_";
  var PURCHASE_KEY = "_trk_purchase_sent";

  function getUserId() {
    var uid = localStorage.getItem(STORAGE_KEY);
    if (uid) return uid;
    uid = "u_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(STORAGE_KEY, uid);
    return uid;
  }

  var userId = getUserId();

<<<<<<< HEAD
=======
  function createSessionId() {
    return "s_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  function getSessionId() {
    var now = Date.now();
    var sid = localStorage.getItem(SESSION_KEY);
    var lastSeenRaw = localStorage.getItem(SESSION_LAST_SEEN_KEY);
    var lastSeen = Number(lastSeenRaw || "0");
    var expired = !Number.isFinite(lastSeen) || now - lastSeen > SESSION_TIMEOUT_MS;

    if (!sid || expired) {
      sid = createSessionId();
      localStorage.setItem(SESSION_KEY, sid);
    }
    localStorage.setItem(SESSION_LAST_SEEN_KEY, String(now));
    return sid;
  }

>>>>>>> dev
  function clean(value) {
    if (value == null) return "";
    return String(value).trim();
  }

  function firstNonEmpty(values) {
    for (var i = 0; i < values.length; i++) {
      var v = clean(values[i]);
      if (v) return v;
    }
    return "";
  }

  function getAttr(selectors, attr) {
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (!el) continue;
      var val = clean(el.getAttribute(attr));
      if (val) return val;
    }
    return "";
  }

  function getText(selectors) {
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (!el) continue;
      var val = clean(el.textContent || el.value || "");
      if (val) return val;
    }
    return "";
  }

  function parsePrice(raw) {
    var src = clean(raw);
    if (!src) return null;
    var match = src.replace(",", ".").match(/-?\d+(?:\.\d+)?/);
    if (!match) return null;
    var num = Number(match[0]);
    return Number.isFinite(num) ? num : null;
  }

  function productFromJsonLd() {
    var scripts = document.querySelectorAll("script[type='application/ld+json']");
    for (var i = 0; i < scripts.length; i++) {
      try {
        var parsed = JSON.parse(scripts[i].textContent || "{}");
        var items = Array.isArray(parsed) ? parsed : (parsed["@graph"] || [parsed]);
        for (var j = 0; j < items.length; j++) {
          var item = items[j] || {};
          var t = item["@type"];
          var isProduct = t === "Product" || (Array.isArray(t) && t.indexOf("Product") !== -1);
          if (!isProduct) continue;
          var offer = Array.isArray(item.offers) ? item.offers[0] : item.offers;
          return {
            product_id: clean(item.sku || item.productID || item.mpn || item.id || ""),
            product_name: clean(item.name || ""),
            price: parsePrice(offer && (offer.price || offer.lowPrice || offer.highPrice)),
            category: clean(item.category || ""),
            currency: clean(offer && offer.priceCurrency || "")
          };
        }
      } catch (e) {}
    }
    return {};
  }

  function pageCategoryFromBreadcrumbs() {
    var crumbs = document.querySelectorAll("[itemprop='itemListElement'] [itemprop='name'], .breadcrumb a, .breadcrumbs a");
    if (!crumbs || !crumbs.length) return "";
    if (crumbs.length >= 2) return clean(crumbs[crumbs.length - 2].textContent);
    return clean(crumbs[0].textContent);
  }

<<<<<<< HEAD
  function getProductContext() {
    var jsonLd = productFromJsonLd();
    var productId = firstNonEmpty([
      jsonLd.product_id,
=======
  function productFromPath(pathname) {
    var p = clean(pathname);
    if (!p) return {};
    // Typical Shoper product URL: /pl/p/Product-Name/1453
    var match = p.match(/\/p\/([^\/]+)\/(\d+)(?:\/)?$/i);
    if (!match) return {};

    var slug = clean(match[1] || "");
    var id = clean(match[2] || "");
    var name = "";
    if (slug) {
      try {
        name = clean(decodeURIComponent(slug).replace(/-/g, " "));
      } catch (e) {
        name = clean(slug.replace(/-/g, " "));
      }
    }

    var out = {};
    if (id) out.product_id = id;
    if (name) out.product_name = name;
    return out;
  }

  function getProductContext() {
    var jsonLd = productFromJsonLd();
    var pathCtx = productFromPath(location.pathname);
    var productId = firstNonEmpty([
      jsonLd.product_id,
      pathCtx.product_id,
>>>>>>> dev
      getAttr(["meta[property='product:retailer_item_id']", "meta[name='product:id']"], "content"),
      getAttr(["[data-product-id]", "[data-item-id]"], "data-product-id"),
      getAttr(["[data-item-id]"], "data-item-id"),
      getAttr(["input[name='product_id']", "input[name='product-id']"], "value")
    ]);
    var productName = firstNonEmpty([
      jsonLd.product_name,
<<<<<<< HEAD
=======
      pathCtx.product_name,
>>>>>>> dev
      getAttr(["meta[property='og:title']"], "content"),
      getText(["h1[itemprop='name']", "h1.product-name", "h1"])
    ]);
    var price = parsePrice(firstNonEmpty([
      jsonLd.price,
      getAttr(["meta[property='product:price:amount']", "meta[name='product:price:amount']"], "content"),
      getAttr(["[itemprop='price']"], "content"),
      getText(["[itemprop='price']", ".price", ".product-price"])
    ]));
    var category = firstNonEmpty([
      jsonLd.category,
      getText(["[itemprop='category']", ".product-category"]),
      pageCategoryFromBreadcrumbs()
    ]);
    var currency = firstNonEmpty([
      jsonLd.currency,
      getAttr(["meta[property='product:price:currency']", "meta[name='product:price:currency']"], "content")
    ]);

    var out = {};
    if (productId) out.product_id = productId;
    if (productName) out.product_name = productName;
    if (price != null) out.price = price;
    if (category) out.category = category;
    if (currency) out.currency = currency;
    return out;
  }

  function isProductPage(ctx) {
    if (ctx.product_id || ctx.product_name) return true;
    var p = location.pathname.toLowerCase();
    return p.indexOf("/product") !== -1 || p.indexOf("/produkt") !== -1 || p.indexOf("/p/") !== -1;
  }

<<<<<<< HEAD
=======
  function isLikelyCheckoutPath(path) {
    var p = clean(path).toLowerCase();
    if (!p) return false;
    return (
      p.indexOf("checkout") !== -1 ||
      p.indexOf("kasa") !== -1 ||
      p.indexOf("zamowienie") !== -1 ||
      p.indexOf("zamow") !== -1
    );
  }

>>>>>>> dev
  function markOnce(key, value) {
    try {
      if (sessionStorage.getItem(key) === value) return false;
      sessionStorage.setItem(key, value);
      return true;
    } catch (e) {
      return true;
    }
  }

  function checkoutStepFromPage(path, pageTitle) {
    var p = (path || "").toLowerCase();
    var t = (pageTitle || "").toLowerCase();

    if (p.indexOf("adres") !== -1 || t.indexOf("adres") !== -1 || document.querySelector("input[name*='address'], input[id*='address']")) {
      return "address";
    }
    if (p.indexOf("dostaw") !== -1 || p.indexOf("shipping") !== -1 || t.indexOf("dostaw") !== -1) {
      return "shipping";
    }
    if (p.indexOf("platn") !== -1 || p.indexOf("payment") !== -1 || t.indexOf("platn") !== -1 || t.indexOf("płatn") !== -1) {
      return "payment";
    }
    if (p.indexOf("podsum") !== -1 || p.indexOf("review") !== -1 || t.indexOf("podsum") !== -1) {
      return "review";
    }
    return "checkout";
  }

  function sendCheckoutStep(step, source) {
    var dedupeKey = CHECKOUT_STEP_PREFIX + step;
    if (!markOnce(dedupeKey, location.pathname)) return;
    send("checkout_step", {
      step: step,
      source: source || "page",
      path: location.pathname
    });
  }

<<<<<<< HEAD
=======
  function normalizeItems(items) {
    if (!Array.isArray(items)) return [];
    return items
      .map(function (it) {
        var quantity = Number(it.quantity || it.qty || 1);
        var price = parsePrice(it.price || it.item_price || it.value || "");
        return {
          product_id: clean(it.product_id || it.item_id || it.id || it.sku || ""),
          name: clean(it.name || it.item_name || it.product_name || ""),
          price: price == null ? 0 : price,
          quantity: Number.isFinite(quantity) && quantity > 0 ? quantity : 1,
        };
      })
      .filter(function (it) {
        return it.product_id || it.name || it.price > 0;
      });
  }

  function purchaseFromDataLayer() {
    var dl = window.dataLayer;
    if (!Array.isArray(dl)) return null;

    for (var i = dl.length - 1; i >= 0; i--) {
      var e = dl[i] || {};
      var ecommerce = e.ecommerce || {};
      var purchase = ecommerce.purchase || {};
      var actionField = purchase.actionField || {};
      var transactionId = clean(
        ecommerce.transaction_id ||
        purchase.transaction_id ||
        actionField.id ||
        e.transaction_id ||
        e.transactionId ||
        ""
      );
      var value = parsePrice(
        ecommerce.value ||
        purchase.value ||
        actionField.revenue ||
        e.value ||
        ""
      );
      var currency = clean(ecommerce.currency || purchase.currency || e.currency || "");
      var items = normalizeItems(ecommerce.items || purchase.items || purchase.products || e.items);

      if (transactionId || value != null || items.length > 0) {
        return {
          order_id: transactionId || null,
          value: value == null ? 0 : value,
          currency: currency || "PLN",
          items: items
        };
      }
    }
    return null;
  }

  function purchaseFromDom() {
    var orderId = firstNonEmpty([
      getText(["[data-order-id]", ".order-id", "#order-id"]),
      getAttr(["[data-order-id]", "meta[name='order:id']"], "data-order-id"),
      getAttr(["meta[name='order:id']"], "content")
    ]);
    var value = parsePrice(firstNonEmpty([
      getAttr(["meta[name='order:value']", "meta[property='order:value']"], "content"),
      getText(["[data-order-total]", ".order-total", ".summary-total", ".total-price"])
    ]));
    var currency = firstNonEmpty([
      getAttr(["meta[name='order:currency']", "meta[property='order:currency']"], "content"),
      "PLN"
    ]);

    if (!orderId && value == null) return null;
    return {
      order_id: orderId || null,
      value: value == null ? 0 : value,
      currency: currency || "PLN",
      items: []
    };
  }

  function getPurchaseContext() {
    return purchaseFromDataLayer() || purchaseFromDom() || {
      order_id: null,
      value: 0,
      currency: "PLN",
      items: []
    };
  }

>>>>>>> dev
  function send(eventName, meta) {
    var sessionId = getSessionId();
    var ua = navigator.userAgent || "";
    var deviceCategory = /tablet|ipad/i.test(ua)
      ? "tablet"
      : /mobi|android|iphone|ipod/i.test(ua)
        ? "mobile"
        : "desktop";
    var enrichedMeta = Object.assign(
      {
        device_category: deviceCategory,
        session_id: sessionId
      },
      meta || {}
    );
    var payload = {
      apiKey: API_KEY,
      event: eventName,
      user_id: userId,
      url: location.href,
      timestamp: Date.now(),
      metadata: enrichedMeta
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

  var productCtx = getProductContext();
  if (isProductPage(productCtx) && markOnce(VIEW_ITEM_KEY, location.pathname)) {
    send("view_item", productCtx);
  }

  var p = location.pathname.toLowerCase();
<<<<<<< HEAD
  var isCheckout = p.indexOf("checkout") !== -1 || p.indexOf("zamowienie") !== -1 || p.indexOf("zamow") !== -1;
=======
  var isCheckout = isLikelyCheckoutPath(p);
>>>>>>> dev
  if (isCheckout && markOnce(CHECKOUT_KEY, location.pathname)) {
    send("begin_checkout", {
      step: "entry",
      path: location.pathname
    });
    sendCheckoutStep(checkoutStepFromPage(location.pathname, document.title), "entry");
  }

  var title = (document.title || "").toLowerCase();
  var isPurchase = p.indexOf("thank") !== -1 || p.indexOf("dziekuj") !== -1 || p.indexOf("potwierdzenie") !== -1 || title.indexOf("dziękuj") !== -1 || title.indexOf("podsumowanie") !== -1;
  if (isPurchase && markOnce(PURCHASE_KEY, location.pathname)) {
<<<<<<< HEAD
    send("purchase", {
      path: location.pathname
    });
=======
    var purchase = getPurchaseContext();
    send("purchase", Object.assign({
      path: location.pathname
    }, purchase));
>>>>>>> dev
  }

  // click + add_to_cart/remove_from_cart/checkout_step — any button / [role=button] / input[type=submit]
  document.addEventListener("click", function (e) {
    var el = e.target.closest("button, [role='button'], input[type='submit'], a");
    if (!el) return;

    var text = (el.textContent || el.value || "").trim().toLowerCase();
    var meta = { tag: el.tagName, text: text.slice(0, 120) };

    var cartWords = ["koszyk", "cart", "add", "dodaj"];
    var isCart = cartWords.some(function (w) { return text.indexOf(w) !== -1; });
    var removeWords = ["usuń", "usun", "remove", "delete", "wyrzuć", "wyrzuc"];
    var isRemove = removeWords.some(function (w) { return text.indexOf(w) !== -1; }) ||
      el.className && String(el.className).toLowerCase().indexOf("remove") !== -1;
<<<<<<< HEAD
    var checkoutWords = ["dalej", "next", "kontynuuj", "przejdź", "przejdz", "zamawiam", "zamów", "zamow", "pay", "płacę", "place order"];
    var isCheckoutAction = checkoutWords.some(function (w) { return text.indexOf(w) !== -1; });
=======
    var checkoutWords = ["dalej", "next", "kontynuuj", "przejdź", "przejdz", "zamawiam", "zamów", "zamow", "do kasy", "kasa", "pay", "płacę", "place order"];
    var isCheckoutAction = checkoutWords.some(function (w) { return text.indexOf(w) !== -1; });
    var href = clean(el.getAttribute("href") || "");
    var goesToCheckout = isLikelyCheckoutPath(href);
>>>>>>> dev

    if (isCart) {
      var ctx = getProductContext();
      send("add_to_cart", Object.assign({}, meta, ctx));
    } else if (isRemove) {
      send("remove_from_cart", Object.assign({}, meta, getProductContext()));
<<<<<<< HEAD
    } else if (isCheckout && isCheckoutAction) {
=======
    } else if (isCheckoutAction || goesToCheckout) {
      if (markOnce(CHECKOUT_KEY, location.pathname)) {
        send("begin_checkout", {
          step: "entry",
          path: location.pathname,
          source: "click_cta"
        });
      }
>>>>>>> dev
      sendCheckoutStep(checkoutStepFromPage(location.pathname, document.title), "click");
    } else {
      send("click", meta);
    }
  }, true);

  document.addEventListener("submit", function (e) {
<<<<<<< HEAD
    if (!isCheckout) return;
    var form = e.target;
    if (!form || !form.tagName) return;
    var id = clean(form.id || "");
    var name = clean(form.getAttribute("name") || "");
=======
    var form = e.target;
    if (!form || !form.tagName) return;
    var formAction = clean(form.getAttribute("action") || "");
    var formId = clean(form.id || "");
    var formName = clean(form.getAttribute("name") || "");
    var formClass = clean(form.className || "");
    var isCheckoutSubmit = isCheckout ||
      isLikelyCheckoutPath(formAction) ||
      /checkout|kasa|zamow|zamów|payment|platn|płatn/i.test(formId + " " + formName + " " + formClass);
    if (!isCheckoutSubmit) return;
    var id = clean(form.id || "");
    var name = clean(form.getAttribute("name") || "");
    if (markOnce(CHECKOUT_KEY, location.pathname)) {
      send("begin_checkout", {
        step: "entry",
        path: location.pathname,
        source: "submit_form"
      });
    }
>>>>>>> dev
    sendCheckoutStep(checkoutStepFromPage(location.pathname, document.title), "submit:" + firstNonEmpty([id, name, "form"]));
  }, true);
})();
