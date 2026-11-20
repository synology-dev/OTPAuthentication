// OTP Authentication DSM ExtJS 3 application
Ext.ns("SYNO.SDS.OTPAuthentication");

SYNO.SDS.OTPAuthentication.Application = Ext.extend(SYNO.SDS.AppInstance, {
  appWindowName: "SYNO.SDS.OTPAuthentication.AppWindow"
});

SYNO.SDS.OTPAuthentication.AppWindow = Ext.extend(SYNO.SDS.AppWindow, {
  constructor: function (cfg) {
    cfg = cfg || {};
    // DSM 7 AppInstance.initInstance only passes appInstance; AppWindow.getIcon/init
    // still read this.jsConfig directly, so copy it before superclass construction.
    if (!cfg.jsConfig && cfg.appInstance && cfg.appInstance.jsConfig) {
      cfg.jsConfig = cfg.appInstance.jsConfig;
    }
    this.state = {
      unlockToken: null,
      csrfToken: null,
      pinConfigured: false,
      clipboardOnly: false,
      username: "",
      query: "",
      codes: {},
      pollTask: null,
      requestSeq: 0,
      page: 1,
      pageSize: 50,
      total: 0
    };
    this._loadPrefs();
    this.baseUrl = "/webman/3rdparty/OTPAuthentication/webapi/";
    this._loadStyles();
    cfg = Ext.apply({
      width: 920,
      height: 620,
      minWidth: 720,
      minHeight: 480,
      resizable: true,
      maximizable: true,
      minimizable: true,
      title: "OTP Authentication",
      layout: "border",
      cls: "otpauthentication-wrap"
    }, cfg);
    this.store = new Ext.data.JsonStore({
      fields: ["id", "issuer", "account", "label", "code", "remaining", "is_shared", "owner", "share_count", "revision", "period", "algorithm", "digits"],
      data: []
    });
    this.grid = this._buildGrid();
    this.toolbar = this._buildToolbar();
    this.statusBar = new Ext.BoxComponent({
      cls: "otpauthentication-status",
      html: ""
    });
    cfg.items = [
      { region: "north", height: 44, border: false, margins: "0 14 0 14", items: [this.toolbar] },
      { region: "center", layout: "fit", border: false, margins: "0 14 0 14", items: [this.grid] },
      { region: "south", height: 24, border: false, margins: "0 14 0 14", items: [this.statusBar] }
    ];
    SYNO.SDS.OTPAuthentication.AppWindow.superclass.constructor.call(this, cfg);
    if (!this.jsConfig && this.appInstance && this.appInstance.jsConfig) {
      this.jsConfig = this.appInstance.jsConfig;
    }
    this.on("afterrender", this._bootstrap, this);
    this.on("show", this._onAppShow, this);
    this.on("beforeclose", this._onBeforeClose, this);
    this.on("destroy", this._cleanup, this);
  },

  _loadStyles: function () {
    if (document.getElementById("otpauthentication-css")) { return; }
    var link = document.createElement("link");
    link.id = "otpauthentication-css";
    link.rel = "stylesheet";
    link.href = "/webman/3rdparty/OTPAuthentication/style.css?v=20261120b";
    document.head.appendChild(link);
  },

  _ensureMsgSkin: function () {
    if (this._msgSkinReady) { return; }
    this._msgSkinReady = true;
    var paint = function () {
      try {
        var d = Ext.Msg.getDialog();
        if (!d) { return; }
        d.addClass("otpauthentication-dialog");
        d.addClass("otpauthentication-msgbox");
        if (d.buttons) {
          Ext.iterate(d.buttons, function (key, btn) {
            if (!btn || !btn.addClass) { return; }
            var label = String(btn.text || (btn.getText && btn.getText()) || "").toLowerCase();
            if (key === "ok" || key === "yes" || label === "ok" || label === "yes") {
              btn.addClass("otpauthentication-btn-primary");
            } else {
              btn.removeClass("otpauthentication-btn-primary");
            }
          });
        }
        if (d.el) {
          d.el.select(".x-btn").each(function (el) {
            var text = String(el.dom.innerText || "").replace(/\s+/g, " ").trim().toLowerCase();
            if (text === "ok" || text === "yes") {
              el.addClass("otpauthentication-btn-primary");
            }
          });
        }
      } catch (e) { /* ignore */ }
    };
    paint();
    try {
      var dlg = Ext.Msg.getDialog();
      if (dlg && dlg.on) {
        dlg.on("show", paint);
      } else {
        Ext.each(["alert", "confirm", "prompt", "show"], function (name) {
          var orig = Ext.Msg[name];
          if (typeof orig !== "function" || orig._otpSkinned) { return; }
          var wrapped = function () {
            var ret = orig.apply(Ext.Msg, arguments);
            window.setTimeout(paint, 0);
            return ret;
          };
          wrapped._otpSkinned = true;
          Ext.Msg[name] = wrapped;
        });
      }
    } catch (e2) { /* ignore */ }
  },

  _buildToolbar: function () {
    var me = this;
    return new Ext.Toolbar({
      cls: "otpauthentication-toolbar",
      items: [
        { xtype: "textfield", emptyText: "Search", width: 180, cls: "otpauthentication-search", enableKeyEvents: true, listeners: {
          keyup: { buffer: 300, fn: function (f) {
            me.state.query = f.getValue();
            me.state.page = 1;
            me.reloadList();
          } }
        }, ref: "../searchField" },
        { text: "Clear", handler: function () {
          me.searchField.setValue("");
          me.state.query = "";
          me.state.page = 1;
          me.reloadList();
        } },
        "->",
        { text: "Add", cls: "otpauthentication-btn-primary", ref: "../btnAdd", handler: function () { me.openEntryDialog(); },
          listeners: { afterrender: function (b) { me.btnAdd = b; } } },
        { text: "Import", ref: "../btnImport", handler: function () { me.openImportDialog(); },
          listeners: { afterrender: function (b) { me.btnImport = b; } } },
        { text: "Export", ref: "../btnExport", handler: function () { me.openExportDialog(); },
          listeners: { afterrender: function (b) { me.btnExport = b; } } },
        "-",
        { text: "Refresh", handler: function () { me.reloadList(true); } },
        { text: "Settings", handler: function () { me.openSettings(); } },
        { text: "Unlock", hidden: true, ref: "../btnLock", handler: function () {
          if (me.state.unlockToken) { me.lockVault(true); }
          else { me.openUnlock(); }
        }, listeners: { afterrender: function (b) {
          me.btnLock = b;
          b.setVisible(!!me.state.pinConfigured);
        } } }
      ]
    });
  },

  _buildGrid: function () {
    var me = this;
    return new Ext.grid.GridPanel({
      store: this.store,
      cls: "otpauthentication-grid",
      border: false,
      stripeRows: true,
      loadMask: true,
      bbar: this._buildPagingBar(),
      columns: [
        { header: "Issuer", dataIndex: "issuer", width: 160 },
        { header: "Account", dataIndex: "account", width: 180 },
        { header: "Code", dataIndex: "code", width: 120, renderer: function (v) {
          var shown = v || "------";
          if (me.state.clipboardOnly && v) { shown = "••••••"; }
          return '<span class="otpauthentication-code">' + Ext.util.Format.htmlEncode(shown) + "</span>";
        }},
        { header: "Time", dataIndex: "remaining", width: 70, renderer: function (v) {
          var rem = parseInt(v, 10);
          var low = !isNaN(rem) && rem <= 5;
          var cls = low ? "otpauthentication-time otpauthentication-time-low" : "otpauthentication-time";
          var text = (v === null || v === undefined || v === "") ? "" : String(v);
          return '<span class="' + cls + '">' + Ext.util.Format.htmlEncode(text) + "</span>";
        }},
        { header: "Owner", dataIndex: "owner", width: 100 },
        { header: "Shares", dataIndex: "share_count", width: 60 }
      ],
      sm: new Ext.grid.RowSelectionModel({ singleSelect: false }),
      viewConfig: { emptyText: "No OTP entries", forceFit: true },
      listeners: {
        rowcontextmenu: function (g, row, e) {
          e.stopEvent();
          var sm = g.getSelectionModel();
          var rec = g.getStore().getAt(row);
          // Keep multi-select when right-clicking an already-selected row (OM-49).
          if (!rec || !sm.isSelected(rec)) {
            sm.selectRow(row);
          }
          me._showRowMenu(e.getXY());
        },
        cellclick: function (g, row, col) {
          // Code column (index 2): click-to-copy (OM-18 / G4)
          if (col !== 2) { return; }
          g.getSelectionModel().selectRow(row);
          me.copySelectedCode(g.getStore().getAt(row));
        },
        celldblclick: function (g, row, col) {
          if (col === 2) { return; }
          me.copySelectedCode(g.getStore().getAt(row));
        }
      }
    });
  },

  _buildPagingBar: function () {
    var me = this;
    var pageSizes = [25, 50, 100, 200];
    var pageCombo = new Ext.form.ComboBox({
      width: 72,
      listWidth: 72,
      mode: "local",
      triggerAction: "all",
      editable: false,
      forceSelection: true,
      value: me.state.pageSize,
      store: pageSizes,
      listClass: "otpauthentication-combo-list",
      cls: "otpauthentication-page-size",
      ctCls: "otpauthentication-page-size-wrap",
      listeners: {
        afterrender: function (c) {
          /* DSM uses <img> trigger sprite — blank src so CSS SVG arrow shows (no `_` artifact) */
          try {
            if (c.trigger && c.trigger.dom) {
              c.trigger.dom.src = Ext.BLANK_IMAGE_URL || "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";
              c.trigger.dom.removeAttribute("width");
              c.trigger.dom.removeAttribute("height");
            }
          } catch (e) { /* ignore */ }
        },
        select: function (c) {
          var size = parseInt(c.getValue(), 10);
          if (!size || size === me.state.pageSize) { return; }
          me.state.pageSize = size;
          me.state.page = 1;
          me.reloadList(true);
        }
      }
    });
    me.pageSizeCombo = pageCombo;
    return new Ext.Toolbar({
      cls: "otpauthentication-paging",
      items: [
        { text: "|<", cls: "otpauthentication-page-nav", ref: "btnFirst", tooltip: "First page",
          handler: function () { me._goPage(1); },
          listeners: { afterrender: function (b) { me.btnPageFirst = b; } } },
        { text: "<<", cls: "otpauthentication-page-nav", ref: "btnPrev", tooltip: "Previous page",
          handler: function () { me._goPage(me.state.page - 1); },
          listeners: { afterrender: function (b) { me.btnPagePrev = b; } } },
        { xtype: "tbtext", text: "1", cls: "otpauthentication-page-num", ref: "pageNum",
          listeners: { afterrender: function (c) { me.pageNumLabel = c; } } },
        { text: ">>", cls: "otpauthentication-page-nav", ref: "btnNext", tooltip: "Next page",
          handler: function () { me._goPage(me.state.page + 1); },
          listeners: { afterrender: function (b) { me.btnPageNext = b; } } },
        { text: ">|", cls: "otpauthentication-page-nav", ref: "btnLast", tooltip: "Last page",
          handler: function () { me._goPage(me._pageCount()); },
          listeners: { afterrender: function (b) { me.btnPageLast = b; } } },
        "->",
        { xtype: "tbtext", text: "Items per page", cls: "otpauthentication-page-label" },
        pageCombo,
        { xtype: "tbtext", text: "0 items", cls: "otpauthentication-page-count",
          listeners: { afterrender: function (c) { me.pageCountLabel = c; } } },
        { xtype: "tbseparator" },
        { text: "↻", cls: "otpauthentication-page-refresh", tooltip: "Refresh",
          handler: function () { me.reloadList(true); } }
      ]
    });
  },

  _pageCount: function () {
    var size = Math.max(1, this.state.pageSize || 50);
    return Math.max(1, Math.ceil((this.state.total || 0) / size));
  },

  _goPage: function (page) {
    var max = this._pageCount();
    page = Math.max(1, Math.min(page || 1, max));
    if (page === this.state.page && this.store.getCount()) {
      // Allow refresh of empty/out-of-range via reloadList callers
    }
    this.state.page = page;
    this.reloadList(true);
  },

  _syncPagingBar: function () {
    var total = this.state.total || 0;
    var pages = this._pageCount();
    var page = Math.max(1, Math.min(this.state.page || 1, pages));
    this.state.page = page;
    if (this.pageNumLabel) {
      this.pageNumLabel.setText(String(page));
    }
    if (this.pageCountLabel) {
      this.pageCountLabel.setText(total + " item" + (total === 1 ? "" : "s"));
    }
    if (this.pageSizeCombo && this.pageSizeCombo.getValue() !== this.state.pageSize) {
      this.pageSizeCombo.setValue(this.state.pageSize);
    }
    var atFirst = page <= 1;
    var atLast = page >= pages || total === 0;
    if (this.btnPageFirst) { this.btnPageFirst.setDisabled(atFirst); }
    if (this.btnPagePrev) { this.btnPagePrev.setDisabled(atFirst); }
    if (this.btnPageNext) { this.btnPageNext.setDisabled(atLast); }
    if (this.btnPageLast) { this.btnPageLast.setDisabled(atLast); }
  },

  _showRowMenu: function (xy) {
    var me = this;
    var sm = this.grid.getSelectionModel();
    var selections = sm.getSelections() || [];
    var rec = sm.getSelected();
    if (!rec) { return; }
    var ownedRecs = [];
    var i;
    for (i = 0; i < selections.length; i++) {
      if (!selections[i].get("is_shared")) {
        ownedRecs.push(selections[i]);
      }
    }
    var multi = selections.length > 1;
    var items = [
      { text: "Copy code", handler: function () { me.copySelectedCode(rec); } }
    ];
    if (!multi && ownedRecs.length === 1) {
      items.push(
        { text: "Edit", handler: function () { me.openEntryDialog(rec); } },
        { text: "Share", handler: function () { me.openShareDialog(rec); } },
        { text: "Reveal secret", handler: function () { me.revealSecret(rec); } }
      );
    }
    if (ownedRecs.length) {
      items.push(
        { text: "Export", handler: function () { me.openExportDialog(); } },
        { text: "Delete", handler: function () { me.deleteEntries(ownedRecs); } }
      );
    }
    var menu = new Ext.menu.Menu({ cls: "otpauthentication-menu", items: items });
    menu.showAt(xy);
  },

  _isAppActive: function () {
    return !this._closing && !this.isDestroyed && !this.destroying;
  },

  _closeAuthDialog: function () {
    var win = this._authDialog;
    this._authDialog = null;
    if (win && !win.isDestroyed) {
      try { win.close(); } catch (e) { /* ignore */ }
    }
  },

  _onAppShow: function () {
    // DSM may reuse the window (show without a fresh afterrender). Prompt auth when locked.
    if (!this._isAppActive()) { return; }
    if (this.state.unlockToken) { return; }
    if (this._authDialog && !this._authDialog.isDestroyed) { return; }
    this._bootstrap();
  },

  _bootstrap: function () {
    var me = this;
    if (!me._isAppActive()) { return; }
    if (me.state.unlockToken) { return; }
    if (me._authDialog && !me._authDialog.isDestroyed) { return; }
    if (me._bootstrapping) { return; }
    me._bootstrapping = true;
    this._closing = false;
    this._ensureMsgSkin();
    this._setLockedUi(true);
    this.setStatus("Checking vault status...");
    this.api("pin.cgi", { method: "status" }, false).then(function (data) {
      me._bootstrapping = false;
      if (!me._isAppActive()) { return; }
      if (me.state.unlockToken) { return; }
      if (me._authDialog && !me._authDialog.isDestroyed) { return; }
      me._setLockedUi(true);
      if (data.package_stopped || data.enabled === false) {
        me.setStatus("OTP Authentication is stopped. Start the package in Package Center.", true);
        return;
      }
      if (data.username) {
        me.state.username = data.username;
        me._loadPrefs();
      }
      if (data.pin_disabled && !data.pin_set) {
        me._setPinConfigured(false);
        me.openNoPinSession();
      } else if (!data.pin_set) {
        me._setPinConfigured(false);
        me.openSetupPin();
      } else {
        me._setPinConfigured(true);
        me.openUnlock();
      }
    }).catch(function (err) {
      me._bootstrapping = false;
      if (!me._isAppActive()) { return; }
      me._setLockedUi(true);
      me.setStatus(err.message || "Unable to reach OTP Authentication API", true);
    });
  },

  setStatus: function (msg, isError) {
    this.statusBar.update('<span class="' + (isError ? "otpauthentication-warn" : "otpauthentication-muted") + '">' +
      Ext.util.Format.htmlEncode(msg || "") + "</span>");
  },

  _formatApiError: function (err) {
    if (!err) { return "Request failed"; }
    if (typeof err === "string") { return err; }
    return err.message || err.code || "Request failed";
  },

  _parseApiResponseError: function (resp) {
    var text = resp && resp.responseText;
    if (text) {
      try {
        var body = Ext.decode(text);
        if (body && body.error) {
          var err = body.error || {};
          return {
            message: err.message || err.code || "Request failed",
            code: err.code,
            extra: err
          };
        }
        if (body && body.success === false) {
          return { message: "Request failed" };
        }
      } catch (e) { /* fall through */ }
    }
    var status = resp && resp.status;
    if (!status || status === 0) {
      return { message: "Network error" };
    }
    return { message: "Request failed (" + status + ")" };
  },

  _dialogErrorItem: function () {
    return {
      xtype: "displayfield",
      name: "_dialogError",
      hideLabel: true,
      value: "",
      itemCls: "otpauthentication-dialog-error-item",
      cls: "otpauthentication-dialog-error"
    };
  },

  _setDialogError: function (win, err) {
    var msg = this._formatApiError(err);
    var fields = win && win.find ? win.find("name", "_dialogError") : null;
    if (fields && fields[0]) {
      fields[0].setValue(Ext.util.Format.htmlEncode(msg));
      return;
    }
    this.setStatus(msg, true);
  },

  _clearDialogError: function (win) {
    var fields = win && win.find ? win.find("name", "_dialogError") : null;
    if (fields && fields[0]) { fields[0].setValue(""); }
  },

  _applyUnlockSession: function (data, statusMsg) {
    this.state.unlockToken = data.unlock_token;
    this.state.csrfToken = data.csrf_token;
    this._setLockedUi(false);
    this.reloadList(true);
    this._startPolling();
    if (statusMsg) { this.setStatus(statusMsg); }
  },

  _isVaultAuthError: function (code) {
    return code === "locked" || code === "unauthorized" || code === "invalid_token";
  },

  /**
   * Re-open vault using server pin.status only (ignore stale client pinConfigured).
   * No PIN → open_nopin / Set up PIN. PIN set → Unlock dialog.
   */
  _recoverVaultSession: function () {
    var me = this;
    if (!me._isAppActive()) { return; }
    if (me._recoveringVault) { return; }
    me._recoveringVault = true;
    me._openingUnlock = false;
    me._closeAuthDialog();
    me._setLockedUi(true);
    me.setStatus("Checking vault status...");
    me.api("pin.cgi", { method: "status" }, false).then(function (data) {
      me._recoveringVault = false;
      if (!me._isAppActive()) { return; }
      if (data.package_stopped || data.enabled === false) {
        me.setStatus("OTP Authentication is stopped. Start the package in Package Center.", true);
        return;
      }
      if (data.username) {
        me.state.username = data.username;
        me._loadPrefs();
      }
      if (!data.pin_set) {
        me._setPinConfigured(false);
        if (data.pin_disabled) {
          me.openNoPinSession();
        } else {
          me.openSetupPin();
        }
        return;
      }
      me._setPinConfigured(true);
      me._showUnlockDialog();
    }).catch(function (err) {
      me._recoveringVault = false;
      if (!me._isAppActive()) { return; }
      if (err && err.code === "unauthorized") {
        me.setStatus("DSM session expired — reload the page or sign in again.", true);
        return;
      }
      me.setStatus((err && err.message) || "Unable to reach OTP Authentication API", true);
    });
  },

  /** Prompt vault access after lock / missing token — always re-check server. */
  _promptVaultAccess: function () {
    this._recoverVaultSession();
  },

  /**
   * API lost vault unlock and/or DSM session.
   * - unauthorized → DSM session dead: soft status, never Unlock PIN.
   * - locked / invalid_token → recover via pin.status (never trust client pinConfigured).
   */
  _handleAuthFailure: function (err) {
    var code = (err && err.code) || "";
    this.lockVault(false, false);
    if (!this._isAppActive()) { return; }
    if (code === "unauthorized") {
      this.setStatus("DSM session expired — reload the page or sign in again.", true);
      return;
    }
    this._recoverVaultSession();
  },

  api: function (endpoint, payload, needUnlock) {
    var me = this;
    payload = payload || {};
    if (needUnlock) {
      if (!me.state.unlockToken) {
        if (me._isAppActive()) { me._promptVaultAccess(); }
        return Promise.reject({ message: "Vault is locked — unlock to continue", code: "locked" });
      }
      payload.unlock_token = me.state.unlockToken;
      payload.csrf_token = me.state.csrfToken;
    }
    var seq = ++me.state.requestSeq;
    var headers = {};
    try {
      if (typeof _S === "function" && _S("SynoToken")) {
        headers["X-SYNO-TOKEN"] = _S("SynoToken");
      }
    } catch (ignore) {}
    if (needUnlock) {
      headers["X-OTP-Unlock"] = me.state.unlockToken || "";
      headers["X-OTP-CSRF"] = me.state.csrfToken || "";
    }
    return new Promise(function (resolve, reject) {
      Ext.Ajax.request({
        url: me.baseUrl + endpoint,
        method: "POST",
        jsonData: payload,
        headers: headers,
        success: function (resp) {
          var body;
          try { body = Ext.decode(resp.responseText); } catch (e) {
            reject({ message: "Invalid server response" });
            return;
          }
          if (!body.success) {
            var err = (body.error || {});
            if (me._isVaultAuthError(err.code)) {
              me._handleAuthFailure(err);
            }
            reject({ message: err.message || err.code || "Request failed", code: err.code, extra: err });
            return;
          }
          body._seq = seq;
          resolve(body.data || {});
        },
        failure: function (resp) {
          var parsed = me._parseApiResponseError(resp);
          if (!parsed.code && resp && resp.status === 401) {
            parsed.code = "unauthorized";
          }
          if (me._isVaultAuthError(parsed.code)) {
            me._handleAuthFailure(parsed);
          }
          reject(parsed);
        }
      });
    });
  },

  openSetupPin: function () {
    var me = this;
    if (!me._isAppActive()) { return; }
    me._closeAuthDialog();
    // First-run Cancel / close without creating a PIN = use vault without PIN
    // (same as empty setup → pin_disabled + unlock session).
    var settled = false;
    var skipToNoPin = function () {
      if (settled || me.state.unlockToken) { return; }
      settled = true;
      me.api("pin.cgi", { method: "setup", pin: "", confirm: "" }, false).then(function (data) {
        if (win && !win.isDestroyed) { win.close(); }
        me._setPinConfigured(false);
        me._applyUnlockSession(data, "Vault unlocked (no PIN).");
      }).catch(function (err) {
        if (win && !win.isDestroyed) { win.close(); }
        if (!me.state.unlockToken) {
          me.openNoPinSession();
        } else {
          me.setStatus(err.message || "Unable to open vault without PIN", true);
        }
      });
    };
    var win = new Ext.Window({
      title: "Set up PIN",
      modal: true,
      width: 360,
      layout: "form",
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      bodyStyle: "padding:16px",
      items: [
        { xtype: "displayfield", value: "Choose a 6–12 digit PIN, or leave both fields empty to disable PIN protection." },
        { xtype: "textfield", fieldLabel: "PIN", inputType: "password", name: "pin", allowBlank: true },
        { xtype: "textfield", fieldLabel: "Confirm", inputType: "password", name: "confirm", allowBlank: true },
        me._dialogErrorItem()
      ],
      buttons: [
        { text: "Cancel", handler: function () {
          // Already unlocked (e.g. Settings → Set PIN): just dismiss.
          if (me.state.unlockToken) {
            settled = true;
            win.close();
            return;
          }
          skipToNoPin();
        } },
        { text: "Create PIN", cls: "otpauthentication-btn-primary", handler: function () {
          me._clearDialogError(win);
          var pin = win.find("name", "pin")[0].getValue();
          var confirm = win.find("name", "confirm")[0].getValue();
          settled = true;
          me.api("pin.cgi", { method: "setup", pin: pin, confirm: confirm }, false).then(function (data) {
            win.close();
            if (data && data.unlock_token) {
              me._setPinConfigured(false);
              me._applyUnlockSession(data, "PIN protection disabled. OTP entries kept.");
            } else {
              me._setPinConfigured(true);
              me.openUnlock();
            }
          }).catch(function (err) {
            settled = false;
            me._setDialogError(win, err);
          });
        }}
      ]
    });
    me._authDialog = win;
    win.on("destroy", function () {
      if (me._authDialog === win) { me._authDialog = null; }
      // X / Esc while locked and no PIN yet → same as Cancel (do not leave UI stuck).
      if (!settled && !me.state.unlockToken && me._isAppActive() && !me._closing) {
        skipToNoPin();
      }
    });
    win.show();
  },

  openUnlock: function () {
    // Toolbar / callers — always confirm PIN exists on server before Unlock dialog (V12b).
    this._recoverVaultSession();
  },

  _showUnlockDialog: function () {
    var me = this;
    if (!me._isAppActive()) { return; }
    me._closeAuthDialog();
    this._setLockedUi(true);
    var doUnlock = function () {
      me._clearDialogError(win);
      var pin = win.find("name", "pin")[0].getValue();
      me.api("pin.cgi", { method: "unlock", pin: pin }, false).then(function (data) {
        win.close();
        me._applyUnlockSession(data);
      }).catch(function (err) {
        me._setDialogError(win, err.message || "Unlock failed");
      });
    };
    var win = new Ext.Window({
      title: "Unlock OTP Authentication",
      modal: true,
      width: 360,
      layout: "form",
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      bodyStyle: "padding:16px",
      items: [
        { xtype: "textfield", fieldLabel: "PIN", inputType: "password", name: "pin", allowBlank: false, enableKeyEvents: true,
          listeners: { specialkey: function (f, e) { if (e.getKey() === e.ENTER) { doUnlock(); } } } },
        me._dialogErrorItem()
      ],
      buttons: [
        { text: "Cancel", handler: function () { win.close(); } },
        { text: "Forgot PIN", handler: function () { win.close(); me.openForgotPin(); } },
        { text: "Unlock", cls: "otpauthentication-btn-primary", handler: doUnlock }
      ]
    });
    me._authDialog = win;
    win.on("destroy", function () {
      if (me._authDialog === win) { me._authDialog = null; }
      // Cancel / close while still locked must keep Unlock label.
      // Successful unlock keeps token — do not force Unlock label.
      if (!me.state.unlockToken) { me._setLockedUi(true); }
    });
    win.show();
  },

  openForgotPin: function () {
    var me = this;
    if (!me._isAppActive()) { return; }
    me._closeAuthDialog();
    this._setLockedUi(true);
    var submit = function () {
      me._clearDialogError(win);
      var password = win.find("name", "password")[0].getValue();
      me.api("pin.cgi", { method: "recover_verify", password: password }, false).then(function (data) {
        win.close();
        me.openRecoverChooser(data.recovery_token);
      }).catch(function (err) {
        me._setDialogError(win, err.message || "Password verification failed");
      });
    };
    var win = new Ext.Window({
      title: "Forgot PIN",
      modal: true,
      width: 420,
      layout: "form",
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      bodyStyle: "padding:16px",
      items: [
        { xtype: "displayfield", value: "Enter your DSM account password to continue. Your OTP entries are kept; this only removes or resets PIN protection." },
        { xtype: "textfield", fieldLabel: "DSM password", inputType: "password", name: "password", allowBlank: false, enableKeyEvents: true,
          listeners: { specialkey: function (f, e) { if (e.getKey() === e.ENTER) { submit(); } } } },
        me._dialogErrorItem()
      ],
      buttons: [
        { text: "Cancel", handler: function () { win.close(); me.openUnlock(); } },
        { text: "Continue", cls: "otpauthentication-btn-primary", handler: submit }
      ]
    });
    me._authDialog = win;
    win.on("destroy", function () {
      if (me._authDialog === win) { me._authDialog = null; }
      if (!me.state.unlockToken) { me._setLockedUi(true); }
    });
    win.show();
  },

  openRecoverChooser: function (recoveryToken) {
    var me = this;
    if (!me._isAppActive()) { return; }
    me._closeAuthDialog();
    this._setLockedUi(true);
    var run = function (action) {
      me._clearDialogError(win);
      me.api("pin.cgi", { method: "recover", recovery_token: recoveryToken, action: action }, false).then(function (data) {
        win.close();
        if (action === "remove") {
          me._setPinConfigured(false);
          me._applyUnlockSession(data, "PIN protection removed. OTP entries kept.");
        } else {
          me.state.unlockToken = null;
          me.state.csrfToken = null;
          me._setPinConfigured(false);
          me._setLockedUi(true);
          me.openSetupPin();
          me.setStatus("Set a new PIN. OTP entries kept.");
        }
      }).catch(function (err) {
        me._setDialogError(win, err.message || "Recovery failed");
      });
    };
    var win = new Ext.Window({
      title: "PIN recovery",
      modal: true,
      width: 440,
      layout: "form",
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      bodyStyle: "padding:16px",
      items: [
        { xtype: "displayfield", value: "Password confirmed. Choose how to continue. OTP entries and shares are kept." },
        me._dialogErrorItem()
      ],
      buttons: [
        { text: "Cancel", handler: function () { win.close(); me.openUnlock(); } },
        { text: "Remove PIN protection", handler: function () { run("remove"); } },
        { text: "Set a new PIN", cls: "otpauthentication-btn-primary", handler: function () { run("reset"); } }
      ]
    });
    me._authDialog = win;
    win.on("destroy", function () {
      if (me._authDialog === win) { me._authDialog = null; }
      if (!me.state.unlockToken) { me._setLockedUi(true); }
    });
    win.show();
  },

  openNoPinSession: function () {
    var me = this;
    if (me._reopeningNoPin) { return; }
    me._reopeningNoPin = true;
    me.api("pin.cgi", { method: "open_nopin" }, false).then(function (data) {
      me._reopeningNoPin = false;
      me._setPinConfigured(false);
      me.state.unlockToken = data.unlock_token;
      me.state.csrfToken = data.csrf_token;
      me._setLockedUi(false);
      me.reloadList(true);
      me._startPolling();
      me.setStatus("Vault unlocked (no PIN).");
    }).catch(function (err) {
      me._reopeningNoPin = false;
      me._setLockedUi(true);
      // unauthorized already surfaced by _handleAuthFailure; do not open Setup/Unlock.
      if (err && err.code === "unauthorized") { return; }
      // Stale "no PIN" client state while server has a PIN.
      if (err && err.code === "pin_exists") {
        me._setPinConfigured(true);
        me.openUnlock();
        return;
      }
      // First-run / pin not disabled yet → Set up PIN (Cancel → disable + open_nopin).
      if (err && err.code === "pin_required") {
        me._setPinConfigured(false);
        me.openSetupPin();
        return;
      }
      me.setStatus(err.message || "Unable to open vault", true);
    });
  },

  lockVault: function (callServer, reopenUnlock) {
    var me = this;
    this._stopPolling();
    this.store.removeAll();
    this.state.codes = {};
    this.state.page = 1;
    this.state.total = 0;
    this._syncPagingBar();
    var token = this.state.unlockToken;
    this.state.unlockToken = null;
    this.state.csrfToken = null;
    this._setLockedUi(true);
    if (callServer && token) {
      this.api("pin.cgi", { method: "lock", unlock_token: token }, false).catch(function () {});
    }
    if (reopenUnlock !== false) {
      this.openUnlock();
    }
  },

  _setPinConfigured: function (configured) {
    this.state.pinConfigured = !!configured;
    if (this.btnLock) {
      this.btnLock.setVisible(!!configured);
    }
  },

  _prefKey: function (name) {
    var u = this.state.username || "";
    return "OTPAuthentication." + name + (u ? "." + u : "");
  },

  _loadPrefs: function () {
    try {
      this.state.clipboardOnly = localStorage.getItem(this._prefKey("clipboardOnly")) === "1";
    } catch (e) {
      this.state.clipboardOnly = false;
    }
  },

  _setClipboardOnly: function (on) {
    this.state.clipboardOnly = !!on;
    try {
      localStorage.setItem(this._prefKey("clipboardOnly"), on ? "1" : "0");
    } catch (e) { /* ignore */ }
    if (this.grid && this.grid.getView) {
      this.grid.getView().refresh();
    }
  },

  _setLockedUi: function (locked) {
    var disable = !!locked;
    Ext.each(["btnAdd", "btnImport", "btnExport"], function (ref) {
      if (this[ref]) { this[ref].setDisabled(disable); }
    }, this);
    if (this.btnLock) {
      this.btnLock.setText(locked ? "Unlock" : "Lock");
      this.btnLock.setDisabled(false);
      this.btnLock.setVisible(!!this.state.pinConfigured);
    }
  },

  reloadList: function (refreshCodes) {
    var me = this;
    if (!me.state.unlockToken) { return; }
    var pageSize = Math.max(1, me.state.pageSize || 50);
    var page = Math.max(1, me.state.page || 1);
    var offset = (page - 1) * pageSize;
    me.api("entries.cgi", {
      method: "list",
      scope: "all",
      q: me.state.query,
      offset: offset,
      limit: pageSize
    }, true).then(function (data) {
      var total = parseInt(data.total, 10);
      if (isNaN(total)) { total = (data.items || []).length; }
      me.state.total = total;
      var maxPage = Math.max(1, Math.ceil(total / pageSize) || 1);
      if (total > 0 && page > maxPage) {
        me.state.page = maxPage;
        me.reloadList(refreshCodes);
        return;
      }
      var rows = (data.items || []).map(function (item) {
        item.code = (me.state.codes[item.id] && me.state.codes[item.id].code) || "";
        item.remaining = (me.state.codes[item.id] && me.state.codes[item.id].remaining) || "";
        return item;
      });
      me.store.loadData(rows);
      me._syncPagingBar();
      me.setStatus(total ? (total + " entr" + (total === 1 ? "y" : "ies")) : "No OTP entries");
      if (refreshCodes !== false) { me.refreshCodes(); }
    }).catch(function (err) { me.setStatus(err.message, true); });
  },

  refreshCodes: function () {
    var me = this;
    if (!me.state.unlockToken) { return; }
    var ids = [];
    me.store.each(function (r) { ids.push(r.get("id")); });
    if (!ids.length) { return; }
    me.api("codes.cgi", { method: "batch", ids: ids }, true).then(function (data) {
      var map = {};
      Ext.each(data.items || [], function (item) { map[item.id] = item; });
      me.state.codes = map;
      me.store.each(function (r) {
        var c = map[r.get("id")];
        if (c) {
          r.beginEdit();
          r.set("code", c.code);
          r.set("remaining", c.remaining);
          r.endEdit();
        }
      });
      me.store.commitChanges();
    }).catch(function (err) {
      // Auth loss handled in api() → _handleAuthFailure; avoid noisy status.
      if (me._isVaultAuthError(err.code)) { return; }
      me.setStatus(err.message || "Code refresh failed", true);
    });
  },

  _startPolling: function () {
    var me = this;
    this._stopPolling();
    this.state.pollTask = Ext.TaskMgr.start({
      run: function () {
        if (!me.state.unlockToken) { return; }
        // Only refresh codes near boundary / every period tick; keep simple 1s countdown locally
        var needFetch = false;
        me.store.each(function (r) {
          var rem = parseInt(r.get("remaining"), 10);
          if (isNaN(rem) || rem <= 1) { needFetch = true; }
          else { r.set("remaining", rem - 1); }
        });
        if (needFetch) { me.refreshCodes(); }
        else { me.store.commitChanges(); }
      },
      interval: 1000
    });
  },

  _stopPolling: function () {
    if (this.state.pollTask) {
      Ext.TaskMgr.stop(this.state.pollTask);
      this.state.pollTask = null;
    }
  },

  copySelectedCode: function (rec) {
    rec = rec || this.grid.getSelectionModel().getSelected();
    if (!rec) { return; }
    var code = rec.get("code");
    var rem = parseInt(rec.get("remaining"), 10);
    var me = this;
    if (!code || rem <= 1) {
      this.refreshCodes();
      this.setStatus("Refreshing code before copy...");
      window.setTimeout(function () {
        var updated = me.grid.getStore().getById(rec.get("id")) || rec;
        var next = updated.get("code");
        if (next) { me._writeClipboard(next); }
      }, 400);
      return;
    }
    this._writeClipboard(code);
  },

  _writeClipboard: function (code) {
    var me = this;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(code).then(function () {
        me.setStatus("Copied");
      }).catch(function () {
        me._manualCopy(code);
      });
    } else {
      this._manualCopy(code);
    }
  },

  _manualCopy: function (code) {
    try {
      var ta = document.createElement("textarea");
      ta.value = code;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      if (ok) {
        this.setStatus("Copied");
        return;
      }
    } catch (e) { /* fall through */ }
    Ext.Msg.alert("Copy code", "Clipboard unavailable. Code: " + code);
  },

  openEntryDialog: function (rec) {
    var me = this;
    var editing = !!rec;
    var win = new Ext.Window({
      title: editing ? "Edit OTP" : "Add OTP",
      modal: true,
      width: 420,
      layout: "form",
      labelWidth: 80,
      defaults: { anchor: "100%" },
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      bodyStyle: "padding:16px",
      items: [
        { xtype: "textfield", fieldLabel: "Issuer", name: "issuer", value: editing ? rec.get("issuer") : "", allowBlank: false },
        { xtype: "textfield", fieldLabel: "Account", name: "account", value: editing ? rec.get("account") : "", allowBlank: false },
        { xtype: "textfield", fieldLabel: "Label", name: "label", value: editing ? rec.get("label") : "" },
        { xtype: "textfield", fieldLabel: editing ? "New secret" : "Secret", name: "secret", allowBlank: editing },
        { xtype: "textarea", fieldLabel: "URI", name: "uri", height: 60, emptyText: "Optional otpauth:// URI" },
        { xtype: "combo", fieldLabel: "Algorithm", name: "algorithm", mode: "local", triggerAction: "all", editable: false,
          listClass: "otpauthentication-combo-list",
          store: ["SHA1", "SHA256", "SHA512"], value: editing ? rec.get("algorithm") : "SHA1" },
        { xtype: "combo", fieldLabel: "Digits", name: "digits", mode: "local", triggerAction: "all", editable: false,
          listClass: "otpauthentication-combo-list",
          store: [["6", "6"], ["8", "8"]], value: editing ? String(rec.get("digits")) : "6" },
        { xtype: "numberfield", fieldLabel: "Period", name: "period", value: editing ? rec.get("period") : 30, minValue: 15, maxValue: 300 },
        { xtype: "textfield", fieldLabel: "PIN", inputType: "password", name: "pin", hidden: !editing },
        me._dialogErrorItem()
      ],
      buttons: [
        { text: "Cancel", handler: function () { win.close(); } },
        { text: "Save", cls: "otpauthentication-btn-primary", handler: function () {
          me._clearDialogError(win);
          var get = function (n) { return win.find("name", n)[0].getValue(); };
          var payload = {
            method: editing ? "update" : "create",
            issuer: get("issuer"),
            account: get("account"),
            label: get("label"),
            secret: get("secret"),
            uri: get("uri"),
            algorithm: get("algorithm"),
            digits: parseInt(get("digits"), 10),
            period: parseInt(get("period"), 10)
          };
          if (editing) {
            payload.id = rec.get("id");
            payload.revision = rec.get("revision");
            payload.pin = get("pin");
          } else {
            payload.request_id = String(new Date().getTime());
          }
          me.api("entries.cgi", payload, true).then(function () {
            win.close();
            me.reloadList(true);
          }).catch(function (err) { me._setDialogError(win, err); });
        }}
      ]
    });
    win.show();
  },

  openShareDialog: function (rec) {
    var me = this;
    var store = new Ext.data.JsonStore({ fields: ["id", "username", "permission", "shared_at"], data: [] });
    var grid = new Ext.grid.GridPanel({
      height: 180,
      store: store,
      cls: "otpauthentication-grid",
      border: false,
      columns: [
        { header: "User", dataIndex: "username", width: 160 },
        { header: "Permission", dataIndex: "permission", width: 80 },
        {
          header: "", width: 70, renderer: function () { return "Revoke"; }
        }
      ],
      listeners: {
        cellclick: function (g, row, col) {
          if (col !== 2) { return; }
          var r = store.getAt(row);
          Ext.Msg.confirm("Revoke share", "Revoke access for " + r.get("username") + "?", function (btn) {
            if (btn !== "yes") { return; }
            me.api("share.cgi", { method: "remove", entry_id: rec.get("id"), share_id: r.get("id") }, true).then(function () {
              load();
              me.reloadList(false);
            }).catch(function (err) { me.setStatus(err.message, true); });
          });
        }
      }
    });
    function load() {
      me.api("share.cgi", { method: "list", entry_id: rec.get("id") }, true).then(function (data) {
        store.loadData(data.items || []);
      });
    }
    var win = new Ext.Window({
      title: "Share: " + rec.get("issuer"),
      modal: true,
      width: 420,
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      items: [
        grid,
        {
          xtype: "form", bodyCssClass: "otpauthentication-dialog-body", bodyStyle: "padding:12px 0 0", items: [
            { xtype: "textfield", fieldLabel: "Username", name: "username", allowBlank: false },
            me._dialogErrorItem()
          ]
        }
      ],
      buttons: [
        { text: "Add share", cls: "otpauthentication-btn-primary", handler: function () {
          me._clearDialogError(win);
          var username = win.items.get(1).getForm().findField("username").getValue();
          me.api("share.cgi", { method: "resolve-recipient", username: username }, true).then(function (info) {
            if (!info.ready) {
              me._setDialogError(win, "User has not set up OTP Authentication yet");
              return;
            }
            return me.api("share.cgi", { method: "add", entry_id: rec.get("id"), username: info.username }, true);
          }).then(function (r) {
            if (r === undefined) { return; }
            load();
            me.reloadList(false);
          }).catch(function (err) { me._setDialogError(win, err); });
        }},
        { text: "Close", handler: function () { win.close(); } }
      ]
    });
    win.show();
    load();
  },

  revealSecret: function (rec) {
    var me = this;
    Ext.Msg.prompt("Confirm PIN", "Enter PIN to reveal secret", function (btn, pin) {
      if (btn !== "ok") { return; }
      me.api("entries.cgi", { method: "reveal", id: rec.get("id"), pin: pin }, true).then(function (data) {
        var box = Ext.Msg.alert("Secret", Ext.util.Format.htmlEncode(data.secret));
        window.setTimeout(function () { try { box.hide(); } catch (e) {} }, 30000);
      }).catch(function (err) { me.setStatus(err.message, true); });
    });
  },

  deleteEntry: function (rec) {
    this.deleteEntries(rec ? [rec] : []);
  },

  deleteEntries: function (recs) {
    var me = this;
    var list = [];
    var i;
    if (!recs || !recs.length) { return; }
    for (i = 0; i < recs.length; i++) {
      if (recs[i] && !recs[i].get("is_shared")) {
        list.push(recs[i]);
      }
    }
    if (!list.length) { return; }
    var msg;
    if (list.length === 1) {
      msg = "Delete " + list[0].get("issuer") + " / " + list[0].get("account") + "?";
    } else {
      msg = "Delete " + list.length + " selected OTP entries?";
    }
    Ext.Msg.confirm("Delete OTP", msg, function (btn) {
      if (btn !== "yes") { return; }
      var ids = [];
      for (i = 0; i < list.length; i++) {
        ids.push(list[i].get("id"));
      }
      me.setStatus("Deleting " + ids.length + "…");
      me.api("entries.cgi", { method: "delete", ids: ids }, true).then(function (data) {
        var n = (data && data.deleted_count) || 0;
        var f = (data && data.failed_count) || 0;
        if (f) {
          me.setStatus("Deleted " + n + "; " + f + " failed", true);
        } else {
          me.setStatus("Deleted " + n + " entr" + (n === 1 ? "y" : "ies") + ".");
        }
        me.reloadList(true);
      }).catch(function (err) {
        me.setStatus(err.message, true);
        me.reloadList(true);
      });
    });
  },

  openImportDialog: function () {
    var me = this;
    if (!me.state.unlockToken) {
      me.setStatus(me.state.pinConfigured ? "Unlock the vault to import" : "Open the vault to import", true);
      me._promptVaultAccess();
      return;
    }
    var win = new Ext.Window({
      title: "Import",
      modal: true,
      width: 640,
      layout: "form",
      labelWidth: 150,
      defaults: { anchor: "100%" },
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      bodyStyle: "padding:16px",
      items: [
        { xtype: "textarea", fieldLabel: "Content", height: 220, name: "content", allowBlank: false,
          emptyText: "Paste otpauth:// lines, or load a .txt / .json file",
          listeners: {
            change: function () { me._scheduleImportDetect(win); },
            afterrender: function (f) {
              var el = f.getEl();
              if (!el) { return; }
              el.on("keyup", function () { me._scheduleImportDetect(win); });
              el.on("paste", function () {
                window.setTimeout(function () { me._syncImportPasswordField(win); }, 0);
              });
            }
          } },
        { xtype: "textfield", fieldLabel: "File", name: "_importFileName", readOnly: true,
          emptyText: "Optional — click to choose .txt or .json",
          listeners: {
            afterrender: function (f) {
              var el = f.getEl();
              if (!el) { return; }
              el.setStyle("cursor", "pointer");
              el.on("click", function () { me._importPickFile(win); });
            }
          } },
        { xtype: "textfield", fieldLabel: "Encryption password", inputType: "password",
          name: "password", hidden: true },
        { xtype: "displayfield", name: "preview", value: "" },
        me._dialogErrorItem()
      ],
      buttons: [
        { text: "Preview", handler: function () {
          me._clearDialogError(win);
          me._importPreview(win).catch(function (err) { me._setDialogError(win, err); });
        }},
        { text: "Confirm import", cls: "otpauthentication-btn-primary", handler: function () {
          me._importConfirm(win);
        }},
        { text: "Cancel", handler: function () { win.close(); } }
      ],
      listeners: {
        close: function () {
          if (win._importDetectTimer) { window.clearTimeout(win._importDetectTimer); }
        }
      }
    });
    win.show();
    me._syncImportPasswordField(win);
  },

  _importContentNeedsPassword: function (content) {
    var s = String(content || "").replace(/^\uFEFF/, "").trim();
    if (!s || s.charAt(0) !== "{") { return false; }
    try {
      var blob = Ext.decode(s);
      return !!(blob && blob.format === "otp-backup-v1");
    } catch (e) {
      return false;
    }
  },

  _setImportFieldRowVisible: function (field, show) {
    if (!field) { return; }
    field.setVisible(show);
    try {
      var row = field.getEl() && field.getEl().up(".x-form-item");
      if (row) { row.setDisplayed(show); }
    } catch (e) { /* ignore */ }
  },

  _syncImportPasswordField: function (win) {
    var contentField = win.find("name", "content")[0];
    var pass = win.find("name", "password")[0];
    var needs = this._importContentNeedsPassword(contentField ? contentField.getValue() : "");
    win._importNeedsPassword = needs;
    this._setImportFieldRowVisible(pass, needs);
    if (!needs && pass) { pass.setValue(""); }
    if (win.doLayout) { win.doLayout(); }
  },

  _scheduleImportDetect: function (win) {
    var me = this;
    if (win._importDetectTimer) { window.clearTimeout(win._importDetectTimer); }
    win._importDetectTimer = window.setTimeout(function () {
      me._syncImportPasswordField(win);
    }, 250);
  },

  _importPickFile: function (win) {
    var me = this;
    var input = document.createElement("input");
    input.type = "file";
    input.accept = ".txt,.json,text/plain,application/json";
    input.style.display = "none";
    document.body.appendChild(input);
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (input.parentNode) { document.body.removeChild(input); }
      if (!file) { return; }
      var name = String(file.name || "");
      if (!/\.(txt|json)$/i.test(name)) {
        me._setDialogError(win, "Choose a .txt or .json file");
        return;
      }
      if (file.size > 2 * 1024 * 1024) {
        me._setDialogError(win, "File too large (max 2 MB)");
        return;
      }
      var reader = new FileReader();
      reader.onload = function () {
        me._clearDialogError(win);
        var text = String(reader.result || "");
        var contentField = win.find("name", "content")[0];
        if (contentField) { contentField.setValue(text); }
        var nameField = win.find("name", "_importFileName")[0];
        if (nameField) { nameField.setValue(name); }
        me.setStatus("Loaded " + name);
        me._syncImportPasswordField(win);
      };
      reader.onerror = function () {
        me._setDialogError(win, "Could not read file");
      };
      reader.readAsText(file);
    });
    input.click();
  },

  _importPreview: function (win) {
    var me = this;
    me._syncImportPasswordField(win);
    var content = win.find("name", "content")[0].getValue();
    var password = win.find("name", "password")[0].getValue();
    if (!String(content || "").trim()) {
      return Promise.reject({ message: "Content required" });
    }
    if (win._importNeedsPassword && !String(password || "")) {
      return Promise.reject({ message: "Encryption password is required" });
    }
    return me.api("backup.cgi", {
      method: "preview",
      content: content,
      password: password
    }, true).then(function (data) {
      win._previewToken = data.preview_token;
      win._previewItems = data.items || [];
      var summary = win._previewItems.map(function (i) {
        return i.issuer + ":" + i.account + " [" + i.status + "]";
      }).join("<br>");
      win.find("name", "preview")[0].setValue(summary || "No entries");
      return data;
    });
  },

  _importConfirm: function (win) {
    var me = this;
    if (!me.state.unlockToken) {
      me.setStatus(me.state.pinConfigured ? "Unlock the vault to import" : "Open the vault to import", true);
      me._promptVaultAccess();
      return;
    }
    me._clearDialogError(win);
    me._importPreview(win).then(function () {
      me._resolveImportConflicts(win._previewItems || [], function (decisions) {
        if (!decisions) { return; }
        me.api("backup.cgi", {
          method: "confirm",
          preview_token: win._previewToken,
          decisions: decisions,
          request_id: String(new Date().getTime())
        }, true).then(function (data) {
          me.setStatus(
            "Imported " + data.added +
            ", overridden " + (data.overridden || 0) +
            ", skipped " + data.skipped
          );
          win.close();
          me.reloadList(true);
        }).catch(function (err) { me._setDialogError(win, err); });
      });
    }).catch(function (err) { me._setDialogError(win, err); });
  },

  _resolveImportConflicts: function (items, done) {
    var me = this;
    var decisions = [];
    var idx = 0;
    var overrideAll = false;
    var skipAll = false;

    function step() {
      if (idx >= items.length) {
        done(decisions);
        return;
      }
      var item = items[idx];
      if (!item || item.status !== "duplicate") {
        decisions.push("import");
        idx += 1;
        step();
        return;
      }
      if (overrideAll) {
        decisions.push("override");
        idx += 1;
        step();
        return;
      }
      if (skipAll) {
        decisions.push("skip");
        idx += 1;
        step();
        return;
      }
      me._askImportConflict(item, function (action) {
        if (!action) {
          done(null);
          return;
        }
        if (action === "override_all") {
          overrideAll = true;
          decisions.push("override");
        } else if (action === "skip_all") {
          skipAll = true;
          decisions.push("skip");
        } else {
          decisions.push(action);
        }
        idx += 1;
        step();
      });
    }
    step();
  },

  _askImportConflict: function (item, done) {
    var issuer = Ext.util.Format.htmlEncode(item.issuer || "");
    var account = Ext.util.Format.htmlEncode(item.account || "");
    var answered = false;
    var finish = function (action) {
      if (answered) { return; }
      answered = true;
      done(action);
    };
    var dlg = new Ext.Window({
      title: "Import conflict",
      modal: true,
      width: 460,
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      bodyStyle: "padding:16px",
      html: "<p>Duplicate entry already exists for <b>" + issuer + "</b> / <b>" + account +
        "</b> (matched by issuer + account).</p><p>Override replaces the existing entry with the imported one.</p>",
      buttons: [
        { text: "Override", cls: "otpauthentication-btn-primary", handler: function () { finish("override"); dlg.close(); } },
        { text: "Skip", handler: function () { finish("skip"); dlg.close(); } },
        { text: "Override All", handler: function () { finish("override_all"); dlg.close(); } },
        { text: "Skip All", handler: function () { finish("skip_all"); dlg.close(); } },
        { text: "Cancel", handler: function () { finish(null); dlg.close(); } }
      ],
      listeners: {
        beforeclose: function () {
          if (!answered) { finish(null); }
        }
      }
    });
    dlg.show();
  },

  openExportDialog: function () {
    var me = this;
    var selected = [];
    var allSel = me.grid.getSelectionModel().getSelections() || [];
    var si;
    for (si = 0; si < allSel.length; si++) {
      if (!allSel[si].get("is_shared")) {
        selected.push(allSel[si]);
      }
    }
    var syncFormatFields = function (win, format) {
      var enc = format !== "plain";
      var setRow = function (field, show) {
        if (!field) { return; }
        field.setVisible(show);
        try {
          var row = field.getEl() && field.getEl().up(".x-form-item");
          if (row) { row.setDisplayed(show); }
        } catch (e) { /* ignore */ }
      };
      var pass = win.find("name", "password")[0];
      var pass2 = win.find("name", "password2")[0];
      var ack = win.find("name", "plain_ack")[0];
      setRow(pass, enc);
      setRow(pass2, enc);
      setRow(ack, !enc);
      if (win.doLayout) { win.doLayout(); }
    };
    var win = new Ext.Window({
      title: "Export",
      modal: true,
      width: 460,
      layout: "form",
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      bodyStyle: "padding:16px",
      labelWidth: 180,
      items: [
        { xtype: "combo", fieldLabel: "Scope", name: "scope", mode: "local", triggerAction: "all", editable: false,
          listClass: "otpauthentication-combo-list",
          store: [["selected", "Selected"], ["all", "All owned"]], value: selected.length ? "selected" : "all" },
        { xtype: "combo", fieldLabel: "Format", name: "format", mode: "local", triggerAction: "all", editable: false,
          listClass: "otpauthentication-combo-list",
          store: [["enc", "Encrypted"], ["plain", "Plaintext"]], value: "enc",
          listeners: {
            select: function (c) { syncFormatFields(win, c.getValue()); }
          } },
        { xtype: "textfield", fieldLabel: "DSM password", inputType: "password", name: "dsm_password", allowBlank: false },
        { xtype: "textfield", fieldLabel: "Encryption password", inputType: "password", name: "password" },
        { xtype: "textfield", fieldLabel: "Confirm encryption password", inputType: "password", name: "password2" },
        { xtype: "checkbox", hideLabel: true, hidden: true, itemCls: "otpauthentication-check",
          name: "plain_ack",
          boxLabel: "I understand plaintext export contains 2FA secrets" },
        me._dialogErrorItem()
      ],
      buttons: [
        { text: "Export", cls: "otpauthentication-btn-primary", handler: function () {
          me._clearDialogError(win);
          var get = function (n) { return win.find("name", n)[0].getValue(); };
          var format = get("format");
          var scope = get("scope");
          var dsmPassword = get("dsm_password");
          var ids = null;
          if (!dsmPassword) {
            me._setDialogError(win, "DSM password required"); return;
          }
          if (scope === "selected") {
            ids = selected.map(function (r) { return r.get("id"); });
            if (!ids.length) { me._setDialogError(win, "No rows selected"); return; }
          }
          if (format === "plain" && !get("plain_ack")) {
            me._setDialogError(win, "Confirm plaintext export risk"); return;
          }
          if (format === "enc") {
            var encPass = String(get("password") || "");
            var encPass2 = String(get("password2") || "");
            if (!encPass) {
              me._setDialogError(win, "Encryption password is required"); return;
            }
            if (encPass !== encPass2) {
              me._setDialogError(win, "Encryption passwords do not match"); return;
            }
          }
          var req = format === "plain" ? {
            method: "export_plain", dsm_password: dsmPassword, ids: ids
          } : {
            method: "export_enc", dsm_password: dsmPassword, password: get("password"), ids: ids
          };
          me.api("backup.cgi", req, true).then(function (data) {
            var text = format === "plain" ? data.content : Ext.encode(data);
            var blob = new Blob([text], { type: "text/plain;charset=utf-8" });
            var url = URL.createObjectURL(blob);
            var a = document.createElement("a");
            a.href = url;
            a.download = format === "plain" ? "otpauthentication-export.txt" : "otpauthentication-export.json";
            a.click();
            URL.revokeObjectURL(url);
            win.close();
            me.setStatus("Export downloaded");
          }).catch(function (err) { me._setDialogError(win, err); });
        }},
        { text: "Cancel", handler: function () { win.close(); } }
      ],
      listeners: {
        afterrender: function () { syncFormatFields(win, "enc"); }
      }
    });
    win.show();
  },

  openSettings: function () {
    var me = this;
    me.api("pin.cgi", { method: "status" }, false).then(function (data) {
      if (data.username) {
        me.state.username = data.username;
        me._loadPrefs();
      }
      var pinBtn = data.pin_set
        ? { text: "Change PIN", cls: "otpauthentication-btn-primary", handler: function () { win.close(); me.openChangePin(); } }
        : { text: "Set PIN", cls: "otpauthentication-btn-primary", handler: function () { win.close(); me.openSetupPin(); } };
      var enc = Ext.util.Format.htmlEncode;
      var settingsRow = function (label, value) {
        return "<div class=\"otpauthentication-settings-row\">" +
          "<span class=\"otpauthentication-settings-label\">" + enc(label) + "</span>" +
          "<span class=\"otpauthentication-settings-value\">" + enc(value) + "</span></div>";
      };
      var win = new Ext.Window({
        title: "Settings",
        modal: true,
        width: 420,
        layout: "auto",
        cls: "otpauthentication-dialog",
        bodyCssClass: "otpauthentication-dialog-body",
        bodyStyle: "padding:12px 16px",
        items: [
          { xtype: "box", cls: "otpauthentication-settings", html:
            "<div class=\"otpauthentication-settings-rows\">" +
            settingsRow("User", data.username || "") +
            settingsRow("App version", data.app_version || "") +
            settingsRow("Idle timeout", data.idle_timeout + "s (read-only)") +
            settingsRow("Absolute timeout", data.absolute_timeout + "s (read-only)") +
            "</div>" },
          { xtype: "container", cls: "otpauthentication-settings-row otpauthentication-settings-pref-row",
            items: [
              { xtype: "box", cls: "otpauthentication-settings-label",
                html: enc("Copy to Clipboard only") },
              { xtype: "checkbox", hideLabel: true, name: "clipboardOnly",
                checked: !!me.state.clipboardOnly,
                cls: "otpauthentication-settings-value",
                listeners: {
                  check: function (cb, checked) { me._setClipboardOnly(checked); }
                }
              }
            ]
          }
        ],
        buttons: [
          pinBtn,
          { text: "Close", handler: function () { win.close(); } }
        ]
      });
      win.show();
    });
  },

  openChangePin: function () {
    var me = this;
    var win = new Ext.Window({
      title: "Change PIN",
      modal: true,
      width: 360,
      layout: "form",
      cls: "otpauthentication-dialog",
      bodyCssClass: "otpauthentication-dialog-body",
      bodyStyle: "padding:16px",
      items: [
        { xtype: "displayfield", value: "Leave New PIN empty to disable PIN protection (OTP entries kept)." },
        { xtype: "textfield", fieldLabel: "Current PIN", inputType: "password", name: "current" },
        { xtype: "textfield", fieldLabel: "New PIN", inputType: "password", name: "pin", allowBlank: true },
        { xtype: "textfield", fieldLabel: "Confirm", inputType: "password", name: "confirm", allowBlank: true },
        me._dialogErrorItem()
      ],
      buttons: [
        { text: "Save", cls: "otpauthentication-btn-primary", handler: function () {
          me._clearDialogError(win);
          me.api("pin.cgi", {
            method: "change",
            current_pin: win.find("name", "current")[0].getValue(),
            pin: win.find("name", "pin")[0].getValue(),
            confirm: win.find("name", "confirm")[0].getValue()
          }, true).then(function (data) {
            win.close();
            if (data && data.unlock_token) {
              me._setPinConfigured(false);
              me._applyUnlockSession(data, "PIN protection disabled. OTP entries kept.");
            } else {
              me._setPinConfigured(true);
              me.lockVault(false);
            }
          }).catch(function (err) { me._setDialogError(win, err); });
        }},
        { text: "Cancel", handler: function () { win.close(); } }
      ]
    });
    win.show();
  },

  _onBeforeClose: function () {
    this._closing = true;
    this._bootstrapping = false;
    this._closeAuthDialog();
    // Lock vault on close, but never reopen Unlock/Setup dialogs.
    this.lockVault(true, false);
    return true;
  },

  _cleanup: function () {
    this._closing = true;
    this._bootstrapping = false;
    this._closeAuthDialog();
    this._stopPolling();
    this.state.unlockToken = null;
    this.state.csrfToken = null;
  }
});