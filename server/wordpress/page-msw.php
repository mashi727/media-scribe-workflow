<?php
/**
 * Template Name: リハ記録 PDF 作成
 *
 * dlab テーマへ置く: page-msw.php ／ assets/js/msw.js
 * 固定ページ（例: /msw/）を作り、テンプレートにこれを選ぶ。
 *
 * このページ自体は秘密を持たない。認証（Google）とデータはすべて
 * api.differance-lab.tokyo（Cloudflare Access ＋ Tunnel → 自宅 WSL）側にある。
 */
if (!defined('ABSPATH')) { exit; }

const MSW_API = 'https://api.differance-lab.tokyo';

add_action('wp_head', function () {
    echo '<meta name="robots" content="noindex,nofollow">' . "\n";
});
wp_enqueue_script('msw', get_template_directory_uri() . '/assets/js/msw.js', [], '0.1.0', true);
wp_add_inline_script('msw', 'window.MSW_API = ' . wp_json_encode(MSW_API) . ';', 'before');

get_header();
?>
<main id="msw" class="msw">
  <h1>リハーサル記録 PDF 作成</h1>

  <section id="msw-login" hidden>
    <p>利用には Google アカウントでのログインが必要です（許可されたアカウントのみ）。</p>
    <a id="msw-login-link" class="button" href="#">Google でログイン</a>
  </section>

  <section id="msw-app" hidden>
    <p class="msw-me">ログイン中: <span id="msw-email"></span></p>

    <form id="msw-form">
      <fieldset>
        <legend>音声</legend>
        <label>音声ファイル（WAV/FLAC 推奨。動画も可）
          <input type="file" name="audio" accept="audio/*,video/*" required></label>
        <label>章立て .txt（任意・Chaptr の書き出し）
          <input type="file" name="chapters" accept=".txt,text/plain"></label>
      </fieldset>
      <fieldset>
        <legend>前提情報</legend>
        <label>表題 <input name="title" placeholder="第3回 合同練習"></label>
        <label>日付 <input name="date" type="date"></label>
        <label>団体 <input name="ensemble"></label>
        <label>指揮者 <input name="conductor" placeholder="○○先生"></label>
        <label>曲目（1行1曲） <textarea name="pieces" rows="3"></textarea></label>
        <label>本番 <input name="concert" placeholder="2026年12月14日 定期演奏会"></label>
        <label>記録者 <input name="author" placeholder="ホルン奏者有志"></label>
        <label>視点（パート） <input name="viewpoint" placeholder="ホルン"></label>
      </fieldset>
      <p class="msw-note">音声は運営者の自宅サーバ内だけで文字起こしし、外部のサービスへは送信しません。原本音声は処理後に削除します。</p>
      <button type="submit">アップロードして作成</button>
      <progress id="msw-progress" max="1" value="0" hidden></progress>
      <p id="msw-status" role="status"></p>
    </form>

    <h2>ジョブ</h2>
    <table class="msw-jobs">
      <thead><tr><th>作成</th><th>表題</th><th>状態</th><th>成果物</th><th></th></tr></thead>
      <tbody id="msw-jobs"></tbody>
    </table>
  </section>

  <p id="msw-offline" hidden>処理サーバに接続できません。しばらくしてから再読み込みしてください。</p>
</main>
<?php
get_footer();
