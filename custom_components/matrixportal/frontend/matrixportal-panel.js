// MatrixPortal: Admin-Panel in der HA-Seitenleiste. Steuerung (an/aus, Helligkeit, Design ...),
// Konfiguration (Entities, Kalender, Kopfzeile) und Gerätedaten (Version, Passwort) je Display.
// Ohne Build-Schritt, folgt dem HA-Theme über CSS-Variablen.

const STYLE = `
:host{display:block;height:100%;overflow:auto;background:var(--primary-background-color);color:var(--primary-text-color);
  font-family:var(--ha-font-family-body,Roboto,system-ui,sans-serif);font-size:14px}
.toolbar{display:flex;align-items:center;gap:8px;height:var(--header-height,56px);padding:0 12px;position:sticky;top:0;z-index:5;
  background:var(--app-header-background-color,var(--primary-color));color:var(--app-header-text-color,#fff);font-size:20px}
.toolbar button{background:none;border:none;color:inherit;cursor:pointer;padding:8px;display:flex}
.toolbar svg{width:24px;height:24px;fill:currentColor}
.wrap{max-width:980px;margin:0 auto;padding:16px}
.card{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:var(--ha-card-border-radius,12px);
  padding:16px;margin-bottom:16px}
h2{font-size:18px;font-weight:500;margin:0;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
h3{font-size:13px;font-weight:500;color:var(--secondary-text-color);margin:18px 0 8px;text-transform:uppercase;letter-spacing:.04em}
.meta{color:var(--secondary-text-color);font-size:12px;margin-top:4px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--disabled-text-color,#999);display:inline-block}
.dot.on{background:var(--success-color,#4caf50)}.dot.bad{background:var(--error-color,#f44)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px 16px}
label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--secondary-text-color)}
label.check{flex-direction:row;align-items:center;gap:8px;color:var(--primary-text-color);font-size:14px}
input,select{background:var(--secondary-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);
  border-radius:6px;padding:7px 9px;font:inherit}
input[type=checkbox]{accent-color:var(--primary-color)}
input[type=range]{padding:0}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button.b{padding:6px 14px;background:transparent;color:var(--primary-color);border:1px solid var(--divider-color);border-radius:18px;
  cursor:pointer;font:inherit;font-weight:500}
button.b:hover{background:color-mix(in srgb,var(--primary-color) 10%,transparent)}
button.b.on,button.b.save{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:var(--primary-color)}
button.b:disabled{opacity:.4;cursor:default}
.info{display:grid;grid-template-columns:1fr 110px;gap:6px 8px}
.cals{display:flex;flex-direction:column;gap:4px;max-height:180px;overflow:auto;padding:4px 0}
.msg{min-height:18px;margin-top:8px}.ok{color:var(--success-color,#4caf50)}.err{color:var(--error-color,#f44)}
.hint{color:var(--secondary-text-color);font-size:12px}
code{background:var(--secondary-background-color);padding:1px 5px;border-radius:4px}
`;

const MENU = '<svg viewBox="0 0 24 24"><path d="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z"/></svg>';
const DESIGN_LABEL = {klassisch: 'Klassisch', kompakt: 'Kompakt', fokus: 'Fokus'};
const HEADER_LABEL = {datum: 'Datum', entities: 'Entities statt Datum', wechselnd: 'Wechselnd'};

function el(tag, props = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'dataset') Object.assign(e.dataset, v);
    else if (k in e) e[k] = v;
    else e.setAttribute(k, v);
  }
  e.append(...children.filter(c => c !== null && c !== undefined));
  return e;
}

class MatrixPortalPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this._data = null;
    this._cards = {};
    this._timer = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._init();
  }

  get hass() { return this._hass; }

  set narrow(v) { this._narrow = v; }

  connectedCallback() {
    if (this._hass && !this._timer) this._timer = setInterval(() => this._refresh(), 5000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
  }

  ws(msg) { return this._hass.callWS(msg); }

  async _init() {
    const root = this.shadowRoot;
    root.innerHTML = '';
    const menu = el('button', {title: 'Menü'});
    menu.innerHTML = MENU;
    menu.onclick = () => this.dispatchEvent(new Event('hass-toggle-menu', {bubbles: true, composed: true}));
    this._list = el('div', {className: 'wrap'});
    root.append(el('style', {textContent: STYLE}), el('div', {className: 'toolbar'}, menu, 'MatrixPortal'), this._list);
    await this._refresh();
    this.connectedCallback();
  }

  async _refresh() {
    try {
      this._data = await this.ws({type: 'matrixportal/devices'});
    } catch (e) {
      this._list.replaceChildren(el('div', {className: 'card err', textContent: 'Fehler: ' + (e.message || e.code)}));
      return;
    }
    const {devices} = this._data;
    if (!devices.length) {
      this._list.replaceChildren(el('div', {className: 'card'},
        el('p', {textContent: 'Noch kein Display. Displays mit Firmware ab 1.0 erscheinen unter Einstellungen → Geräte & Dienste.'})));
      this._cards = {};
      return;
    }
    const seen = new Set();
    for (const d of devices) {
      seen.add(d.entry_id);
      let card = this._cards[d.entry_id];
      if (!card) {
        card = this._cards[d.entry_id] = this._buildCard(d);
        this._list.append(card.root);
      }
      card.update(d);
    }
    for (const id of Object.keys(this._cards)) {
      if (!seen.has(id)) { this._cards[id].root.remove(); delete this._cards[id]; }
    }
    if (this._list.firstChild && !this._list.firstChild.classList?.contains('card')) this._list.firstChild.remove();
  }

  // ── Datalists aus den HA-Zuständen ──
  _entities(filter) {
    return Object.values(this._hass.states).filter(filter)
      .map(s => [s.entity_id, s.attributes.friendly_name || s.entity_id])
      .sort((a, b) => a[1].localeCompare(b[1]));
  }

  _datalist(id, filter) {
    return el('datalist', {id}, ...this._entities(filter).map(([e, n]) => el('option', {value: e, label: n})));
  }

  _buildCard(d) {
    const self = this;
    const id = d.entry_id;
    const msg = el('div', {className: 'msg'});
    const say = (text, cls = 'ok') => { msg.className = 'msg ' + cls; msg.textContent = text; };
    const act = async (promise, ok) => {
      try { await promise; if (ok) say(ok); setTimeout(() => self._refresh(), 600); }
      catch (e) { say('Fehler: ' + (e.message || e.code || e), 'err'); }
    };
    const set = values => act(self.ws({type: 'matrixportal/set', entry_id: id, ...values}));
    const cmd = (command, ok) => act(self.ws({type: 'matrixportal/command', entry_id: id, command}), ok);

    // Kopf
    const dot = el('span', {className: 'dot'});
    const title = el('span');
    const meta = el('div', {className: 'meta'});
    const pwText = el('code', {textContent: '••••••••'});
    const pwBtn = el('button', {className: 'b', textContent: 'zeigen'});
    let pwShown = false;
    pwBtn.onclick = () => { pwShown = !pwShown; card.update(card.last); };
    const nameIn = el('input', {value: d.name, maxLength: 31, style: 'width:180px'});
    const renameBtn = el('button', {className: 'b', textContent: 'Umbenennen'});
    renameBtn.onclick = () => act(self.ws({type: 'matrixportal/rename', entry_id: id, name: nameIn.value}),
      'Umbenannt, das Display startet neu.');

    // Steuerung
    const onBtn = el('button', {className: 'b', textContent: 'An'});
    const offBtn = el('button', {className: 'b', textContent: 'Aus'});
    onBtn.onclick = () => set({on: true});
    offBtn.onclick = () => set({on: false});
    const bright = el('input', {type: 'range', min: 1, max: 255});
    bright.onchange = () => set({brightness: +bright.value});
    const design = el('select', {}, ...self._data.designs.map(v => el('option', {value: v, textContent: DESIGN_LABEL[v] || v})));
    design.onchange = () => set({design: design.value});
    const header = el('select', {}, ...self._data.headers.map(v => el('option', {value: v, textContent: HEADER_LABEL[v] || v})));
    header.onchange = () => set({header: header.value});
    const demo = el('input', {type: 'checkbox'});
    demo.onchange = () => set({demo: demo.checked});
    const pac = el('input', {type: 'number', min: 0, max: 1440, style: 'width:90px'});
    pac.onchange = () => set({pac_every: +pac.value});
    const controls = el('div', {className: 'grid'},
      el('label', {}, 'Anzeige', el('div', {className: 'row'}, onBtn, offBtn)),
      el('label', {}, 'Helligkeit', bright),
      el('label', {}, 'Design', design),
      el('label', {}, 'Kopfzeile', header),
      el('label', {}, 'Pac-Man alle X Minuten (0 = aus)', pac),
      el('label', {className: 'check'}, demo, 'Demo-Modus (nicht gespeichert)'));
    const actions = el('div', {className: 'row', style: 'margin-top:10px'},
      el('button', {className: 'b', textContent: 'Pac-Man jetzt', onclick: () => cmd('pacman')}),
      el('button', {className: 'b', textContent: 'Wochenübersicht', onclick: () => cmd('week')}),
      el('button', {className: 'b', textContent: 'Identifizieren', onclick: () => cmd('identify', 'Das Display zeigt 15 s Name und IP.')}),
      el('button', {className: 'b', textContent: 'Kalender neu laden', onclick: () => cmd('refresh', 'Kalender werden neu geladen.')}),
      el('button', {className: 'b', textContent: 'Neustart', onclick: () => confirm('Display neu starten?') && cmd('restart', 'Startet neu ...')}));

    // Konfiguration
    const uid = 'mp' + id.slice(0, 8);
    const isPower = s => s.entity_id.startsWith('sensor.') && ['W', 'kW', 'MW'].includes(s.attributes.unit_of_measurement);
    const isTemp = s => s.entity_id.startsWith('climate.') || (s.entity_id.startsWith('sensor.') && s.attributes.device_class === 'temperature');
    const lists = el('div', {},
      self._datalist(uid + 'p', isPower),
      self._datalist(uid + 't', isTemp),
      self._datalist(uid + 'w', s => s.entity_id.startsWith('weather.')),
      self._datalist(uid + 'c', s => s.entity_id.startsWith('calendar.')),
      self._datalist(uid + 'a', s => !s.entity_id.startsWith('calendar.')));
    const ent = (list, ph) => el('input', {placeholder: ph, maxLength: 63, autocomplete: 'off', list: uid + list});
    const f = {
      solar: ent('p', 'sensor.pv_leistung'),
      office: ent('p', 'sensor.schreibtisch_leistung'),
      room: ent('t', 'climate.buero'),
      weather: ent('w', 'weather.forecast_home'),
      work_calendar: ent('c', 'calendar.arbeit'),
      solar_max: el('input', {type: 'number', min: 100, max: 65000}),
      office_max: el('input', {type: 'number', min: 100, max: 65000}),
      blockers: el('input', {maxLength: 63}),
      tz: el('input', {maxLength: 63}),
    };
    const cals = el('div', {className: 'cals'});
    const calNames = self._entities(s => s.entity_id.startsWith('calendar.'));
    const calBoxes = calNames.map(([e, n]) => {
      const c = el('input', {type: 'checkbox', value: e});
      cals.append(el('label', {className: 'check'}, c, `${n} (${e})`));
      return c;
    });
    if (!calNames.length) cals.append(el('span', {className: 'hint', textContent: 'Keine calendar.*-Entities in HA.'}));
    const info = [];
    const infoGrid = el('div', {className: 'info'});
    for (let i = 0; i < 4; i++) {
      const e = ent('a', i ? '' : 'sensor.bad_luftfeuchte'), l = el('input', {maxLength: 7, placeholder: i ? '' : 'Bad'});
      info.push([e, l]);
      infoGrid.append(e, l);
    }
    const tzBtn = el('button', {className: 'b', textContent: 'aus HA übernehmen'});
    tzBtn.onclick = () => { if (self._data.ha_tz) f.tz.value = self._data.ha_tz; };
    const save = el('button', {className: 'b save', textContent: 'Konfiguration speichern'});
    let loaded = false;
    const fill = c => {
      for (const k of Object.keys(f)) f[k].value = c[k] ?? '';
      const sel = new Set(c.calendars || []);
      calBoxes.forEach(b => { b.checked = sel.has(b.value); });
      info.forEach(([e, l], i) => { e.value = c.info?.[i]?.entity || ''; l.value = c.info?.[i]?.label || ''; });
    };
    save.onclick = () => {
      const config = {
        solar: f.solar.value.trim(), office: f.office.value.trim(), room: f.room.value.trim(),
        weather: f.weather.value.trim(), work_calendar: f.work_calendar.value.trim(),
        calendars: calBoxes.filter(b => b.checked).map(b => b.value),
        info: info.filter(([e]) => e.value.trim()).map(([e, l]) => ({entity: e.value.trim(), label: l.value.trim()})),
        blockers: f.blockers.value, tz: f.tz.value.trim(),
        solar_max: +f.solar_max.value || 800, office_max: +f.office_max.value || 400,
      };
      act(self.ws({type: 'matrixportal/save_config', entry_id: id, config}).then(r => {
        fill(r.config);
        say(r.pushed ? 'Gespeichert und ans Display geschickt.' : 'Gespeichert. Das Display bekommt es, sobald es verbunden ist.');
      }));
    };
    const configBox = el('div', {},
      el('h3', {textContent: 'Seitenleiste'}),
      el('div', {className: 'grid'},
        el('label', {}, 'Solar-Leistung (W / kW)', f.solar),
        el('label', {}, 'Solar: voller Balken bei W', f.solar_max),
        el('label', {}, 'Schreibtisch-Verbrauch', f.office),
        el('label', {}, 'Schreibtisch: voller Balken bei W', f.office_max),
        el('label', {}, 'Raumtemperatur (sensor.* oder climate.*)', f.room),
        el('label', {}, 'Wetter (Kopfzeile)', f.weather)),
      el('h3', {textContent: 'Kalender'}),
      el('div', {className: 'grid'},
        el('label', {}, 'Kalender für die Termine', cals),
        el('div', {},
          el('label', {}, 'Arbeitskalender', f.work_calendar),
          el('p', {className: 'hint', textContent: 'Ganztägige Kürzel (MA, TD, U …) färben die Wochenleiste: MA grün, TD lila, ohne Kürzel (N) weiß. Letzte Zeile: morgen Büro / Tagdienst.'}),
          el('label', {}, 'Blocker: Titel enthält eines dieser Wörter (Komma)', f.blockers))),
      el('h3', {textContent: 'Kopfzeile: Entities (Entity / Kurzname, max. 7 Zeichen)'}),
      infoGrid,
      el('p', {className: 'hint', textContent: 'Erscheinen je nach Kopfzeilen-Modus statt des Datums oder im Wechsel. Ganztägige Termine kommen immer dazu.'}),
      el('h3', {textContent: 'Zeitzone (POSIX)'}),
      el('div', {className: 'row'}, f.tz, tzBtn),
      el('div', {className: 'row', style: 'margin-top:14px'}, save),
      lists);

    const root = el('div', {className: 'card'},
      el('h2', {}, dot, title),
      meta,
      el('div', {className: 'row', style: 'margin-top:8px'}, nameIn, renameBtn,
        el('span', {className: 'hint', textContent: 'Web-UI / OTA: Benutzer admin, Passwort'}), pwText, pwBtn),
      el('h3', {textContent: 'Steuerung'}), controls, actions,
      configBox, msg);

    const busy = e => self.shadowRoot.activeElement === e;
    const card = {
      root, last: d,
      update(d) {
        card.last = d;
        const st = d.status || {};
        const bad = d.auth_failed;
        dot.className = 'dot' + (bad ? ' bad' : d.connected ? ' on' : '');
        title.textContent = d.name;
        const state = bad ? 'mit anderem HA gekoppelt (am Gerät: System → Kopplung lösen)'
          : d.connected ? 'verbunden' : 'nicht verbunden';
        const fw = self._data.firmware && d.version && !d.version.startsWith('v' + self._data.firmware + '+')
          ? ` · Update auf ${self._data.firmware} verfügbar (Einstellungen → Updates)` : '';
        meta.replaceChildren(`${state} · ${d.host} · Firmware ${d.version || '?'}` +
          (st.rssi ? ` · WLAN ${st.rssi} dBm` : '') + (st.events !== undefined ? ` · ${st.events} Termine heute` : '') + fw,
          d.last_error ? el('div', {className: 'err', textContent: 'Display meldet: ' + d.last_error}) : '',
          ' · ', el('a', {href: `http://${d.host}/`, target: '_blank', textContent: 'Web-UI'}));
        pwText.textContent = pwShown ? (d.password || '(keins)') : '••••••••';
        pwBtn.textContent = pwShown ? 'verbergen' : 'zeigen';
        onBtn.classList.toggle('on', st.on === true);
        offBtn.classList.toggle('on', st.on === false);
        for (const e of [onBtn, offBtn, bright, design, header, demo, pac, ...actions.children]) e.disabled = !d.connected;
        if (!busy(bright) && st.brightness) bright.value = st.brightness;
        if (!busy(design) && st.design) design.value = st.design;
        if (!busy(header) && st.header) header.value = st.header;
        if (!busy(pac) && st.pac_every !== undefined) pac.value = st.pac_every;
        demo.checked = !!st.demo;
        if (!busy(nameIn) && nameIn.value !== d.name && document.activeElement !== self) nameIn.value = d.name;
        if (!loaded && d.config) { fill(d.config); loaded = true; }
        configBox.hidden = !d.config;
      },
    };
    return card;
  }
}

customElements.define('matrixportal-panel', MatrixPortalPanel);
