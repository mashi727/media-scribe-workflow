#!/usr/bin/env python3
"""
対話ログ（Markdown）をLaTeX形式に変換するスクリプト
"""

import re
import sys
from pathlib import Path


def escape_latex(text: str) -> str:
    """LaTeX特殊文字をエスケープ"""
    # バックスラッシュを最初に処理
    text = text.replace('\\', '\\textbackslash{}')
    # その他の特殊文字
    replacements = [
        ('{', '\\{'),
        ('}', '\\}'),
        ('$', '\\$'),
        ('%', '\\%'),
        ('&', '\\&'),
        ('#', '\\#'),
        ('_', '\\_'),
        ('^', '\\textasciicircum{}'),
        ('~', '\\textasciitilde{}'),
        ('<', '\\textless{}'),
        ('>', '\\textgreater{}'),
        ('|', '\\textbar{}'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def process_inline_code(text: str) -> str:
    """インラインコード `code` を \\texttt{code} に変換"""
    def replace_inline(match):
        code = match.group(1)
        return f'\\texttt{{{code}}}'
    return re.sub(r'`([^`]+)`', replace_inline, text)


def process_markdown_formatting(text: str) -> str:
    """Markdown書式をLaTeXに変換"""
    text = re.sub(r'\*\*([^*]+)\*\*', r'\\textbf{\1}', text)
    text = re.sub(r'\*([^*]+)\*', r'\\textit{\1}', text)
    return text


def extract_date_from_filename(filename: str) -> str:
    """ファイル名から日付を抽出"""
    match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if match:
        return match.group(1)
    return "Unknown"


def convert_dialog_file(input_path: Path) -> str:
    """単一のMarkdownファイルをLaTeX形式に変換"""
    content = input_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    date_str = extract_date_from_filename(input_path.name)

    output_lines = []
    in_code_block = False
    code_lang = ""
    code_buffer = []
    in_userbox = False

    # ヘッダー情報を抽出
    message_count = ""
    for line in lines[:10]:
        if line.startswith("メッセージ数:"):
            message_count = line.replace("メッセージ数:", "").strip()
            break

    # セクションヘッダー
    output_lines.append(f"\\section{{{date_str}の対話記録}}")
    if message_count:
        output_lines.append(f"\\noindent この日のメッセージ数: {message_count}")
    output_lines.append("")

    def close_userbox_if_open():
        """userboxが開いていれば閉じる"""
        nonlocal in_userbox
        if in_userbox:
            output_lines.append("\\end{userbox}")
            output_lines.append("")
            in_userbox = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # コードブロックの開始
        if line.startswith('```') and not in_code_block:
            in_code_block = True
            code_lang = line[3:].strip()
            code_buffer = []
            i += 1
            continue

        # コードブロックの終了
        if line.startswith('```') and in_code_block:
            in_code_block = False
            code_content = '\n'.join(code_buffer)

            # 空のコードブロックはスキップ
            if not code_content.strip():
                i += 1
                continue

            # lstlistingで出力
            if code_lang and code_lang.lower() in ['python', 'bash', 'sh', 'zsh', 'javascript', 'js', 'json', 'yaml', 'latex', 'tex']:
                lang_map = {'sh': 'bash', 'zsh': 'bash', 'js': 'javascript', 'tex': 'latex'}
                lang = lang_map.get(code_lang.lower(), code_lang.lower())
                output_lines.append(f"\\begin{{lstlisting}}[language={lang}]")
            else:
                output_lines.append("\\begin{lstlisting}")

            output_lines.append(code_content)
            output_lines.append("\\end{lstlisting}")
            output_lines.append("")
            code_buffer = []
            i += 1
            continue

        # コードブロック内
        if in_code_block:
            code_buffer.append(line)
            i += 1
            continue

        # ヘッダー行（開発ログのタイトル）をスキップ
        if line.startswith('# 開発ログ'):
            i += 1
            continue

        # メッセージ数の行をスキップ
        if line.startswith('メッセージ数:'):
            i += 1
            continue

        # 区切り線
        if line.strip() == '---':
            i += 1
            continue

        # ユーザーメッセージの開始
        if line.startswith('## 👤 User'):
            close_userbox_if_open()
            time_match = re.search(r'\((\d{2}:\d{2}:\d{2})\)', line)
            time_str = time_match.group(1) if time_match else ""

            output_lines.append(f"\\begin{{userbox}}[title={{問い ({time_str})}}]")
            in_userbox = True
            i += 1
            continue

        # アシスタントメッセージの開始
        if line.startswith('## 🤖 Assistant'):
            close_userbox_if_open()
            time_match = re.search(r'\((\d{2}:\d{2}:\d{2})\)', line)
            time_str = time_match.group(1) if time_match else ""

            output_lines.append(f"\\paragraph{{回答 ({time_str})}}")
            i += 1
            continue

        # ツール呼び出しの行
        if line.startswith('[Tool:'):
            tool_match = re.match(r'\[Tool:\s*(\w+)\](.*)', line)
            if tool_match:
                tool_name = tool_match.group(1)
                tool_args = tool_match.group(2).strip()

                escaped_args = escape_latex(tool_args) if tool_args else ""
                if escaped_args:
                    # 長い引数は省略
                    if len(escaped_args) > 80:
                        escaped_args = escaped_args[:77] + "..."
                    output_lines.append(f"\\noindent{{\\footnotesize \\texttt{{[{tool_name}]}} {escaped_args}}}")
                else:
                    output_lines.append(f"\\noindent{{\\footnotesize \\texttt{{[{tool_name}]}}}}")
                output_lines.append("")
            i += 1
            continue

        # 空行
        if not line.strip():
            output_lines.append("")
            i += 1
            continue

        # 通常のテキスト行
        escaped_line = escape_latex(line)
        escaped_line = process_inline_code(escaped_line)
        escaped_line = process_markdown_formatting(escaped_line)

        # リスト項目の変換
        if escaped_line.strip().startswith('- '):
            item_content = escaped_line.strip()[2:]
            output_lines.append("\\begin{itemize}")
            output_lines.append(f"\\item {item_content}")
            i += 1
            while i < len(lines) and lines[i].strip().startswith('- '):
                item = escape_latex(lines[i].strip()[2:])
                item = process_inline_code(item)
                item = process_markdown_formatting(item)
                output_lines.append(f"\\item {item}")
                i += 1
            output_lines.append("\\end{itemize}")
            output_lines.append("")
            continue

        # 番号付きリスト
        if re.match(r'^\d+\.\s', escaped_line.strip()):
            match = re.match(r'^(\d+)\.\s(.+)', escaped_line.strip())
            if match:
                item_content = match.group(2)
                output_lines.append("\\begin{enumerate}")
                output_lines.append(f"\\item {item_content}")
                i += 1
                while i < len(lines) and re.match(r'^\d+\.\s', lines[i].strip()):
                    m = re.match(r'^\d+\.\s(.+)', lines[i].strip())
                    if m:
                        item = escape_latex(m.group(1))
                        item = process_inline_code(item)
                        item = process_markdown_formatting(item)
                        output_lines.append(f"\\item {item}")
                    i += 1
                output_lines.append("\\end{enumerate}")
                output_lines.append("")
                continue

        output_lines.append(escaped_line)
        output_lines.append("")
        i += 1

    # 最後のuserboxを閉じる
    close_userbox_if_open()

    return '\n'.join(output_lines)


def main():
    dev_logs_dir = Path("/Users/mashi/works/git/portfolio/rehearsal-workflow/dev_logs")
    output_dir = Path("/Users/mashi/Dropbox/01_Projects/00_Works/git/portfolio/rehearsal-workflow/dev_logs_tex")

    log_files = sorted(dev_logs_dir.glob("conversation_*.md"))

    all_content = []

    for log_file in log_files:
        print(f"Converting: {log_file.name}", file=sys.stderr)
        try:
            latex_content = convert_dialog_file(log_file)
            all_content.append(latex_content)
            all_content.append("\\newpage")
            all_content.append("")
        except Exception as e:
            print(f"Error processing {log_file.name}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

    output_path = output_dir / "dialog_full_converted.tex"
    output_path.write_text('\n'.join(all_content), encoding='utf-8')
    print(f"Output written to: {output_path}", file=sys.stderr)
    print(f"Total lines: {len(all_content)}", file=sys.stderr)


if __name__ == "__main__":
    main()
