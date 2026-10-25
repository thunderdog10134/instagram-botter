/**
 * Pullshot Connect — Google Apps Script web app in Josh's Google account.
 * It is the Instagram OAuth redirect and the token vault for Clip Autopilot.
 * Script Properties (set once in J1): IG_APP_ID, IG_APP_SECRET, PULL_KEY, CONTACT_EMAIL.
 * Deploy: Web app, execute as Me, access Anyone. The /exec URL is the redirect URI in the Meta app.
 * No secrets live in this file.
 */
var SCOPES = 'instagram_business_basic,instagram_business_content_publish,instagram_business_manage_insights,instagram_business_manage_comments,instagram_business_manage_messages'; // manage_messages added Oct 25 (comment-to-DM private replies, approved by Josh); every account re-taps Allow once after this is deployed
var API = 'https://graph.instagram.com/v25.0';

function props_() { return PropertiesService.getScriptProperties(); }
function selfUrl_() { return ScriptApp.getService().getUrl(); }
function json_(obj) { return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON); }
function page_(title, bodyHtml) {
  var html = '<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>' + title + '</title><style>body{font:16px/1.5 -apple-system,system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 16px;color:#111;background:#fff}' +
    'a.btn{display:inline-block;background:#111;color:#fff;padding:12px 18px;border-radius:10px;text-decoration:none;margin:12px 0}small{color:#666}</style>' + bodyHtml;
  return HtmlService.createHtmlOutput(html).setTitle(title).addMetaTag('viewport', 'width=device-width, initial-scale=1');
}
function keyOk_(k) { var want = props_().getProperty('PULL_KEY'); return !!want && k === want; }

function authorizeUrl_(kind) {
  return 'https://www.instagram.com/oauth/authorize?client_id=' + encodeURIComponent(props_().getProperty('IG_APP_ID')) +
    '&redirect_uri=' + encodeURIComponent(selfUrl_()) + '&scope=' + encodeURIComponent(SCOPES) +
    '&response_type=code&state=' + encodeURIComponent(kind || 'pool');
}

function doGet(e) {
  var p = (e && e.parameter) || {};
  if (p.code) return finishConnect_(String(p.code).replace(/#_$/, ''), p.state || 'pool');
  if (p.error) return page_('Not connected', '<h2>Not connected</h2><p>' + (p.error_description || p.error) + '</p><p>You can close this page.</p>');
  if (p.action === 'pull') {
    if (!keyOk_(p.key)) return json_({ error: 'key' });
    var all = props_().getProperties(), out = [], since = p.since || '';
    Object.keys(all).forEach(function (k) {
      if (k.indexOf('acct:') !== 0) return;
      try { var a = JSON.parse(all[k]); if (!since || (a.connectedAt || '') >= since || (a.updatedAt || '') >= since) out.push(a); } catch (err) {}
    });
    return json_({ accounts: out });
  }
  if (p.action === 'forget') {
    if (!keyOk_(p.key)) return json_({ error: 'key' });
    props_().deleteProperty('acct:' + String(p.username || '').toLowerCase());
    return json_({ ok: true });
  }
  if (p.page === 'privacy') return page_('Privacy', privacyHtml_());
  if (p.page === 'terms') return page_('Terms', termsHtml_());
  var kind = p.kind || 'pool';
  return page_('Pullshot connect',
    '<h2>Connect your Instagram page</h2><p>Pullshot posts short clips to your professional Instagram account and reads their views and comments. ' +
    'You stay the owner and can disconnect any time in Instagram → Settings → Website permissions → Apps and websites.</p>' +
    '<a class="btn" href="' + authorizeUrl_(kind) + '" target="_top">Connect with Instagram</a>' +
    '<p><small><a href="' + selfUrl_() + '?page=privacy" target="_top">Privacy</a> · <a href="' + selfUrl_() + '?page=terms" target="_top">Terms</a></small></p>');
}

function doPost(e) {
  var p = (e && e.parameter) || {};
  var body = {};
  try { body = JSON.parse((e.postData && e.postData.contents) || '{}'); } catch (err) {}
  var key = p.key || body.key;
  if (!keyOk_(key)) return json_({ error: 'key' });
  if ((p.action || body.action) === 'update') {
    var u = String(body.username || '').toLowerCase();
    var cur = props_().getProperty('acct:' + u);
    if (!cur) return json_({ error: 'unknown account' });
    var a = JSON.parse(cur);
    a.token = body.token || a.token;
    a.expiresAt = body.expiresAt || a.expiresAt;
    a.updatedAt = new Date().toISOString();
    props_().setProperty('acct:' + u, JSON.stringify(a));
    return json_({ ok: true });
  }
  return json_({ error: 'action' });
}

function finishConnect_(code, kind) {
  var P = props_();
  var res = UrlFetchApp.fetch('https://api.instagram.com/oauth/access_token', {
    method: 'post', muteHttpExceptions: true,
    payload: { client_id: P.getProperty('IG_APP_ID'), client_secret: P.getProperty('IG_APP_SECRET'),
      grant_type: 'authorization_code', redirect_uri: selfUrl_(), code: code }
  });
  var js = {};
  try { js = JSON.parse(res.getContentText()); } catch (err) {}
  if (js.data && js.data.length) js = js.data[0];
  if (!js.access_token) return page_('Not connected', '<h2>Not connected</h2><p>Instagram said: ' + (js.error_message || res.getContentText()).toString().slice(0, 300) + '</p><p>Try the connect link again.</p>');
  var longRes = UrlFetchApp.fetch('https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=' +
    encodeURIComponent(P.getProperty('IG_APP_SECRET')) + '&access_token=' + encodeURIComponent(js.access_token), { muteHttpExceptions: true });
  var lj = {};
  try { lj = JSON.parse(longRes.getContentText()); } catch (err) {}
  var token = lj.access_token || js.access_token;
  var expiresIn = lj.expires_in || 3600;
  var meRes = UrlFetchApp.fetch(API + '/me?fields=id,user_id,username,account_type&access_token=' + encodeURIComponent(token), { muteHttpExceptions: true });
  var me = {};
  try { me = JSON.parse(meRes.getContentText()); } catch (err) {}
  if (!me.username) return page_('Not connected', '<h2>Not connected</h2><p>Could not read the account. Is it a professional (Creator or Business) account?</p>');
  var now = new Date();
  var rec = { username: String(me.username).toLowerCase(), id: me.id, user_id: me.user_id || js.user_id, account_type: me.account_type,
    token: token, expiresAt: new Date(now.getTime() + expiresIn * 1000).toISOString(), kind: kind, connectedAt: now.toISOString(), updatedAt: now.toISOString() };
  P.setProperty('acct:' + rec.username, JSON.stringify(rec));
  return page_('Connected', '<h2>Connected as @' + rec.username + '</h2><p>You can close this page.</p>');
}

function privacyHtml_() {
  var c = props_().getProperty('CONTACT_EMAIL') || '';
  return '<h2>Privacy</h2><p>Pullshot Connect lets the owner of a professional Instagram account authorize Pullshot to publish short video clips to that account and to read the account\'s basic profile, post insights and comments.</p>' +
    '<p><b>What we store:</b> the account\'s username and id and an access token, kept in the Pullshot owner\'s private Google account; post ids and view counts, kept on a private dashboard. We do not store passwords, messages, followers\' personal data or payment details.</p>' +
    '<p><b>What we do not do:</b> we never sell or share data, never like, follow or message other accounts, and never post anything the owner has not agreed to.</p>' +
    '<p><b>Disconnecting:</b> remove the app in Instagram → Settings → Website permissions → Apps and websites, or email us and we delete the token within 7 days.</p>' +
    (c ? '<p><b>Contact:</b> ' + c + '</p>' : '');
}
function termsHtml_() {
  return '<h2>Terms</h2><p>By connecting an account you confirm you own or manage it and agree that Pullshot may publish clips to it under the written agreement you made with us, and read its insights and comments to report results.</p>' +
    '<p>You can disconnect at any time. Posted clips stay up unless you ask us to remove them. Pullshot is provided as is; our liability is limited to the fees you paid in the last 30 days.</p>';
}
