/*
 * リハ記録 PDF 作成ページ（dlab テーマ assets/js/msw.js）
 *
 * api.differance-lab.tokyo は Cloudflare Access の内側。未ログインだと Access が
 * fetch を弾く（CORS エラーに見える）ので、そのときはログインリンクを出し、
 * ブラウザごと API の /login へ遷移させて Google ログイン → このページへ戻す。
 *
 * 文字列は textContent でしか DOM に入れない（innerHTML を使わない）。
 */
(function () {
  'use strict';
  var API = window.MSW_API;
  var $ = function (id) { return document.getElementById(id); };

  function api(path, opts) {
    opts = opts || {};
    opts.credentials = 'include';
    return fetch(API + path, opts).then(function (r) {
      if (r.status === 204) { return null; }
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) {
          var d = body && body.detail;
          var err = new Error((d && (d.message || d)) || ('HTTP ' + r.status));
          err.status = r.status; err.body = d;
          throw err;
        }
        return body;
      });
    });
  }

  function showLogin() {
    $('msw-login-link').href = API + '/login?next=' + encodeURIComponent(location.href);
    $('msw-login').hidden = false;
  }

  function el(tag, text, attrs) {
    var e = document.createElement(tag);
    if (text != null) { e.textContent = text; }
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }

  var STATUS = { uploading: '送信中', queued: '待機中', running: '処理中', done: '完了', failed: '失敗' };

  function renderJobs(jobs) {
    var tb = $('msw-jobs');
    tb.replaceChildren();
    jobs.forEach(function (j) {
      var tr = el('tr');
      tr.appendChild(el('td', new Date(j.created_at * 1000).toLocaleString('ja-JP')));
      tr.appendChild(el('td', j.meta.title || j.meta.filename));
      var st = el('td', STATUS[j.status] || j.status);
      if (j.status === 'running' && j.stage) { st.appendChild(el('div', j.stage, { 'class': 'msw-stage' })); }
      if (j.status === 'failed' && j.error) { st.appendChild(el('pre', j.error, { 'class': 'msw-error' })); }
      tr.appendChild(st);
      var files = el('td');
      j.files.forEach(function (f) {
        files.appendChild(el('a', f, { href: API + '/api/jobs/' + j.id + '/files/' + f }));
        files.appendChild(document.createTextNode(' '));
      });
      tr.appendChild(files);
      var act = el('td');
      if (j.status !== 'running') {
        var b = el('button', '削除', { type: 'button' });
        b.onclick = function () {
          if (!confirm('このジョブと関連ファイルを削除します')) { return; }
          api('/api/jobs/' + j.id, { method: 'DELETE' }).then(refresh, alert);
        };
        act.appendChild(b);
      }
      tr.appendChild(act);
      tb.appendChild(tr);
    });
  }

  function refresh() {
    return api('/api/jobs').then(renderJobs).then(function () {
      $('msw-offline').hidden = true;
    }, function () { $('msw-offline').hidden = false; });
  }

  // offset 付きで分割送信。失敗したらサーバの受信済み位置から再開する
  function upload(job, file, onProgress) {
    var size = job.chunk_bytes;
    function send(offset, retries) {
      if (offset >= file.size) { return Promise.resolve(); }
      var chunk = file.slice(offset, Math.min(offset + size, file.size));
      return api('/api/jobs/' + job.id + '/input?offset=' + offset, {
        method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' }, body: chunk
      }).then(function (r) {
        onProgress(r.received / file.size);
        return send(r.received, 5);
      }, function (e) {
        if (retries <= 0) { throw e; }
        var resume = (e.status === 409 && e.body && e.body.received != null) ? e.body.received : offset;
        return new Promise(function (ok) { setTimeout(ok, 2000 * (6 - retries)); })
          .then(function () { return send(resume, retries - 1); });
      });
    }
    return send(0, 5);
  }

  function onSubmit(ev) {
    ev.preventDefault();
    var f = ev.target, v = f.elements;  // f.title は form 自身の属性と衝突するので elements 経由
    var audio = v.audio.files[0], chapters = v.chapters.files[0];
    var btn = f.querySelector('button[type=submit]'), bar = $('msw-progress'), status = $('msw-status');
    var meta = {
      filename: audio.name, size: audio.size,
      title: v.title.value, date: v.date.value, ensemble: v.ensemble.value,
      conductor: v.conductor.value, concert: v.concert.value, author: v.author.value,
      viewpoint: v.viewpoint.value,
      pieces: v.pieces.value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean)
    };
    btn.disabled = true; bar.hidden = false; bar.value = 0;
    status.textContent = 'ジョブを作成しています';
    var job;
    api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(meta) })
      .then(function (j) {
        job = j;
        if (!chapters) { return null; }
        return api('/api/jobs/' + job.id + '/chapters', { method: 'PUT', body: chapters });
      })
      .then(function () {
        status.textContent = 'アップロード中';
        return upload(job, audio, function (p) { bar.value = p; status.textContent = 'アップロード中 ' + Math.floor(p * 100) + '%'; });
      })
      .then(function () { return api('/api/jobs/' + job.id + '/submit', { method: 'POST' }); })
      .then(function () { status.textContent = '受け付けました。処理状況は下の一覧に出ます。'; f.reset(); refresh(); })
      .catch(function (e) { status.textContent = 'エラー: ' + e.message; })
      .finally(function () { btn.disabled = false; bar.hidden = true; });
  }

  api('/api/me').then(function (me) {
    $('msw-email').textContent = me.email;
    $('msw-app').hidden = false;
    $('msw-form').addEventListener('submit', onSubmit);
    refresh();
    setInterval(refresh, 10000);
  }, function (e) {
    // 未ログインは Access が弾くので、ネットワークエラー（TypeError）か 401/403 になる
    if (e.status === 403) { $('msw-login').querySelector('p').textContent = e.message; }
    showLogin();
  });
})();
