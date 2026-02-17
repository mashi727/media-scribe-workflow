#!/usr/bin/env python3
"""
Claude Code のjsonlログをMarkdown形式に変換するスクリプト
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict


def parse_timestamp(ts_str: str) -> datetime:
    """ISO形式のタイムスタンプをパース"""
    # 2025-12-23T22:29:49.811Z
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except:
        return None


def format_time(dt: datetime) -> str:
    """時刻をHH:MM:SS形式に"""
    if dt is None:
        return "??:??:??"
    # JST (UTC+9)
    from datetime import timedelta
    jst = dt + timedelta(hours=9)
    return jst.strftime("%H:%M:%S")


def extract_text_content(content) -> str:
    """メッセージコンテンツからテキストを抽出"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    texts.append(item.get('text', ''))
                elif item.get('type') == 'tool_result':
                    # ツール結果は省略
                    pass
                elif item.get('type') == 'tool_use':
                    tool_name = item.get('name', 'Unknown')
                    texts.append(f"[Tool: {tool_name}]")
            elif isinstance(item, str):
                texts.append(item)
        return '\n'.join(texts)
    return str(content)


def process_jsonl(jsonl_path: Path) -> dict:
    """jsonlファイルを処理して日付別のメッセージを抽出"""
    messages_by_date = defaultdict(list)

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            entry_type = entry.get('type')
            timestamp = entry.get('timestamp')

            if timestamp is None:
                continue

            dt = parse_timestamp(timestamp)
            if dt is None:
                continue

            # JST日付
            from datetime import timedelta
            jst_dt = dt + timedelta(hours=9)
            date_str = jst_dt.strftime("%Y-%m-%d")

            # ユーザーメッセージ
            if entry_type == 'user':
                message = entry.get('message', {})
                content = message.get('content', '')
                text = extract_text_content(content)

                # tool_resultのみの場合はスキップ
                if isinstance(content, list):
                    has_text = any(
                        isinstance(item, str) or
                        (isinstance(item, dict) and item.get('type') == 'text')
                        for item in content
                    )
                    if not has_text:
                        continue

                if text.strip():
                    messages_by_date[date_str].append({
                        'role': 'user',
                        'time': format_time(dt),
                        'content': text,
                        'timestamp': dt
                    })

            # アシスタントメッセージ
            elif entry_type == 'assistant':
                message = entry.get('message', {})
                content = message.get('content', '')
                text = extract_text_content(content)

                if text.strip():
                    messages_by_date[date_str].append({
                        'role': 'assistant',
                        'time': format_time(dt),
                        'content': text,
                        'timestamp': dt
                    })

    return messages_by_date


def format_markdown(date_str: str, messages: list) -> str:
    """メッセージをMarkdown形式に整形"""
    # タイムスタンプでソート
    messages.sort(key=lambda x: x.get('timestamp') or datetime.min)

    lines = [
        f"# 開発ログ {date_str}",
        "",
        f"メッセージ数: {len(messages)}",
        "",
        "---",
        ""
    ]

    for msg in messages:
        role = msg['role']
        time = msg['time']
        content = msg['content']

        if role == 'user':
            lines.append(f"## 👤 User ({time})")
        else:
            lines.append(f"## 🤖 Assistant ({time})")

        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    return '\n'.join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: convert_jsonl_to_md.py <jsonl_file> [output_dir]", file=sys.stderr)
        sys.exit(1)

    jsonl_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")

    if not jsonl_path.exists():
        print(f"Error: {jsonl_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Processing: {jsonl_path}", file=sys.stderr)
    messages_by_date = process_jsonl(jsonl_path)

    for date_str, messages in sorted(messages_by_date.items()):
        if not messages:
            continue

        output_file = output_dir / f"conversation_{date_str}.md"
        md_content = format_markdown(date_str, messages)

        output_file.write_text(md_content, encoding='utf-8')
        print(f"Written: {output_file} ({len(messages)} messages)", file=sys.stderr)


if __name__ == "__main__":
    main()
