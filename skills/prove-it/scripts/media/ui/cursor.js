(function () {
  var style = { accent: "#f59e0b", ink: "#111827" };
  var LAYER = 2147483646;
  var cursor = null;
  var pos = { x: 0, y: 0 };

  function center(el) {
    var r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2, r: r };
  }

  function layer(tag, css) {
    var el = document.createElement(tag);
    el.setAttribute("aria-hidden", "true");
    el.style.cssText = "position:fixed;left:0;top:0;pointer-events:none;z-index:" + LAYER + ";" + css;
    document.documentElement.appendChild(el);
    return el;
  }

  function makeCursor() {
    if (cursor) return cursor;
    cursor = layer("div", "width:24px;height:24px;will-change:transform;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35));");
    cursor.innerHTML =
      '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M3 2 L3 19 L7.6 14.8 L10.6 21.6 L13.6 20.3 L10.7 13.6 L17 13.6 Z" fill="#fff" stroke="' +
      style.ink + '" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    return cursor;
  }

  function moveTo(x, y) {
    pos = { x: x, y: y };
    makeCursor().style.transform = "translate(" + (x - 3) + "px," + (y - 2) + "px)";
  }

  function ripple(x, y) {
    var d = layer("div", "width:14px;height:14px;border-radius:50%;border:3px solid " + style.accent +
      ";background:" + style.accent + "33;transform:translate(" + (x - 7) + "px," + (y - 7) + "px);");
    d.animate(
      [{ transform: "translate(" + (x - 7) + "px," + (y - 7) + "px) scale(1)", opacity: 1 },
       { transform: "translate(" + (x - 7) + "px," + (y - 7) + "px) scale(4.2)", opacity: 0 }],
      { duration: 650, easing: "cubic-bezier(.2,.7,.3,1)", fill: "forwards" });
    setTimeout(function () { d.remove(); }, 700);
  }

  function outline(el, holdMs) {
    var radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
    var o = layer("div", "border:2.5px solid " + style.accent + ";border-radius:" + (radius + 5) +
      "px;box-shadow:0 0 0 4px " + style.accent + "33;opacity:0;");
    var alive = true;
    function track() {
      if (!alive) return;
      var r = el.getBoundingClientRect();
      o.style.left = (r.left - 5) + "px";
      o.style.top = (r.top - 5) + "px";
      o.style.width = (r.width + 10) + "px";
      o.style.height = (r.height + 10) + "px";
      requestAnimationFrame(track);
    }
    track();
    o.animate([{ opacity: 0 }, { opacity: 1, offset: 0.12 }, { opacity: 1, offset: 0.8 }, { opacity: 0 }],
      { duration: holdMs, fill: "forwards" });
    setTimeout(function () { alive = false; o.remove(); }, holdMs + 50);
  }

  function glide(from, to, ms, easing) {
    var c = makeCursor();
    c.getAnimations().forEach(function (a) { a.cancel(); });
    c.animate(
      [{ transform: "translate(" + (from.x - 3) + "px," + (from.y - 2) + "px)" },
       { transform: "translate(" + (to.x - 3) + "px," + (to.y - 2) + "px)" }],
      { duration: ms, easing: easing, fill: "forwards" });
    setTimeout(function () { c.getAnimations().forEach(function (a) { a.cancel(); }); moveTo(to.x, to.y); }, ms);
  }

  function clickPoint(el) {
    var r = el.getBoundingClientRect();
    return { x: r.left + r.width * 0.78, y: r.top + r.height * 0.62 };
  }

  function press() {
    var t = cursor.style.transform;
    cursor.animate([{ transform: t + " scale(1)" }, { transform: t + " scale(.82)" }, { transform: t + " scale(1)" }],
      { duration: 220, easing: "ease-out" });
  }

  var ROLES = {
    button: "button,input[type=button],input[type=submit],input[type=reset],[role=button]",
    link: "a[href],[role=link]",
    textbox: "input:not([type]),input[type=text],input[type=email],input[type=password],input[type=search]," +
      "input[type=tel],input[type=url],input[type=number],textarea,[role=textbox],[contenteditable=true]",
    checkbox: "input[type=checkbox],[role=checkbox]",
    radio: "input[type=radio],[role=radio]",
    combobox: "select,[role=combobox]",
    option: "option,[role=option]",
    heading: "h1,h2,h3,h4,h5,h6,[role=heading]",
    img: "img,[role=img]"
  };
  var nextId = 0;

  function norm(t) { return (t || "").replace(/\s+/g, " ").trim(); }

  function shown(el) {
    for (var n = el; n && n !== document.documentElement; n = n.parentElement) {
      var s = getComputedStyle(n);
      if (s.display === "none" || s.visibility === "hidden") return false;
    }
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  function labelsOf(el) {
    var out = [];
    var by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach(function (id) { var l = document.getElementById(id); if (l) out.push(l.innerText); });
    if (el.labels) Array.prototype.forEach.call(el.labels, function (l) { out.push(l.innerText); });
    return out;
  }

  function nameOf(el) {
    var aria = el.getAttribute("aria-label");
    if (aria) return norm(aria);
    var labels = labelsOf(el);
    if (labels.length) return norm(labels.join(" "));
    if (el.tagName === "INPUT" && /^(button|submit|reset)$/i.test(el.type)) return norm(el.value);
    if (el.tagName === "IMG") return norm(el.alt);
    var text = norm(el.innerText || el.textContent);
    return text || norm(el.getAttribute("title") || el.getAttribute("placeholder"));
  }

  function candidates(spec) {
    if (spec.css) return document.querySelectorAll(spec.css);
    if (spec.testid) return document.querySelectorAll('[data-testid="' + CSS.escape(spec.testid) + '"]');
    if (spec.role) return document.querySelectorAll(ROLES[spec.role] || '[role="' + CSS.escape(spec.role) + '"]');
    if (spec.placeholder) return document.querySelectorAll("[placeholder]");
    if (spec.label) return document.querySelectorAll("input,textarea,select,[role=textbox],[role=combobox]");
    return document.querySelectorAll("body *");
  }

  function pick(els, want, get) {
    var lower = want.toLowerCase(), tiers = [[], [], []];
    els.forEach(function (el) {
      var v = get(el);
      if (v === want) tiers[0].push(el);
      else if (v.toLowerCase() === lower) tiers[1].push(el);
      else if (v.toLowerCase().indexOf(lower) >= 0) tiers[2].push(el);
    });
    for (var i = 0; i < 3; i++) if (tiers[i].length) return tiers[i];
    return [];
  }

  function find(spec) {
    var els = Array.prototype.filter.call(candidates(spec), shown);
    if (spec.role && spec.name) els = pick(els, spec.name, nameOf);
    else if (spec.label) els = pick(els, spec.label, function (el) { return norm(labelsOf(el).join(" ") || el.getAttribute("aria-label")); });
    else if (spec.placeholder) els = pick(els, spec.placeholder, function (el) { return norm(el.getAttribute("placeholder")); });
    else if (spec.text) {
      els = pick(els, spec.text, function (el) { return norm(el.innerText); });
      els = els.filter(function (el) { return !els.some(function (o) { return o !== el && el.contains(o); }); });
    }
    return els[0] || null;
  }

  window.__proveit = {
    resolve: function (spec) {
      var el = find(spec);
      if (!el) return "";
      var id = el.getAttribute("data-proveit-id");
      if (!id) { id = "t" + (++nextId) + "-" + Date.now().toString(36); el.setAttribute("data-proveit-id", id); }
      var r = el.getBoundingClientRect();
      if (r.top < 0 || r.bottom > innerHeight) el.scrollIntoView({ block: "center" });
      return '[data-proveit-id="' + id + '"]';
    },
    aim: function (selector, moveMs) {
      var to = clickPoint(document.querySelector(selector));
      glide({ x: pos.x, y: pos.y }, to, moveMs, "cubic-bezier(.45,.05,.25,1)");
      return [to.x, to.y];
    },
    tap: function (selector, outlineMs) {
      var el = document.querySelector(selector);
      press();
      ripple(pos.x, pos.y);
      outline(el, outlineMs || 900);
      return true;
    },
    away: function () { glide(pos, { x: pos.x + 34, y: pos.y + 30 }, 380, "ease-out"); return true; },
    at: function () { return [pos.x, pos.y]; },
    moveTo: function (x, y) { moveTo(x, y); return true; },
    setStyle: function (s) { for (var k in s) style[k] = s[k]; if (cursor) { cursor.remove(); cursor = null; } return true; },
    place: function (selector, dx, dy, within) {
      var c = center(document.querySelector(selector));
      var box = within && document.querySelector(within) ? document.querySelector(within).getBoundingClientRect()
        : { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
      var x = Math.max(box.left + 12, Math.min(box.right - 24, c.x + (dx === undefined ? -190 : dx)));
      var y = Math.max(box.top + 12, Math.min(box.bottom - 24, c.y + (dy === undefined ? -130 : dy)));
      moveTo(x, y);
      return [x, y];
    },
    click: function (selector, moveMs, outlineMs) {
      var el = document.querySelector(selector);
      var to = clickPoint(el);
      glide({ x: pos.x, y: pos.y }, to, moveMs, "cubic-bezier(.45,.05,.25,1)");
      setTimeout(function () {
        press();
        ripple(to.x, to.y);
        outline(el, outlineMs || 1200);
        setTimeout(function () { el.click(); }, 90);
        setTimeout(function () { glide(to, { x: to.x + 34, y: to.y + 30 }, 380, "ease-out"); }, 420);
      }, moveMs + 5);
      return [to.x, to.y];
    }
  };
  return true;
})();
