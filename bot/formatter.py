"""
Telegram Message Formatter & Safe HTML Sender for Arush Agent.

Converts standard GitHub-flavored Markdown (headers, tables, bold, italic,
fenced code blocks, inline code, links, blockquotes, horizontal rules) into clean,
valid, mobile-friendly Telegram HTML, and safely chunks long messages (>4000 chars)
while preserving open HTML tag boundaries across split points.
"""

import html
import re
import logging
from typing import List, Tuple, Dict, Any, Optional

try:
    from aiogram import Bot
    from aiogram.types import Message, InlineKeyboardMarkup
    from aiogram.enums import ParseMode
    HAS_AIOGRAM = True
except ImportError:
    HAS_AIOGRAM = False
    Bot = object  # type: ignore
    Message = object  # type: ignore
    InlineKeyboardMarkup = object  # type: ignore
    ParseMode = object  # type: ignore

logger = logging.getLogger("arush-agent.formatter")

TELEGRAM_MAX_MESSAGE_LENGTH = 4000  # Safe threshold below Telegram 4096 limit


def is_table_delimiter(line: str) -> bool:
    """Checks whether a line is a markdown table separator (e.g. |:---|:---:|---:|)."""
    stripped = line.strip().strip("|").strip()
    if not stripped:
        return False
    cells = [c.strip() for c in stripped.split("|")]
    if not cells:
        return False
    return all(re.match(r"^:?-{2,}:?$", c) for c in cells)


def convert_markdown_tables(text: str) -> str:
    """
    Detects markdown tables and converts them into mobile-friendly structured cards.
    2 columns:
      • **Key:** Value
    3+ columns:
      ▫️ **PrimaryCol**
        • **Col2:** Val2
        • **Col3:** Val3
    """
    lines = text.splitlines()
    output_lines: List[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        # Look ahead for a table separator line
        if "|" in line and (i + 1 < n) and is_table_delimiter(lines[i + 1]):
            header_line = line
            raw_headers = [c.strip() for c in header_line.strip().strip("|").split("|")]

            # Collect subsequent data rows
            data_rows: List[List[str]] = []
            j = i + 2
            while j < n and "|" in lines[j] and lines[j].strip():
                row_cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                while len(row_cells) < len(raw_headers):
                    row_cells.append("")
                data_rows.append(row_cells)
                j += 1

            table_formatted: List[str] = []
            if len(raw_headers) == 2:
                for row in data_rows:
                    k, v = row[0], row[1]
                    if k or v:
                        table_formatted.append(f"• **{k}:** {v}")
            else:
                for idx, row in enumerate(data_rows):
                    primary_val = row[0]
                    card_parts = [f"▫️ **{primary_val}**"]
                    for col_idx in range(1, len(raw_headers)):
                        h_name = raw_headers[col_idx]
                        c_val = row[col_idx]
                        if c_val:
                            # Auto-wrap commands or paths in backticks if not already formatted
                            is_code_col = any(w in h_name.lower() for w in ("command", "target", "path", "file", "query"))
                            if is_code_col and not c_val.startswith("`") and not c_val.startswith("\x00"):
                                card_parts.append(f"  • **{h_name}:** `{c_val}`")
                            else:
                                card_parts.append(f"  • **{h_name}:** {c_val}")
                    table_formatted.append("\n".join(card_parts))
                    if idx < len(data_rows) - 1:
                        table_formatted.append("")  # Blank spacer between cards

            output_lines.extend(table_formatted)
            i = j
        else:
            output_lines.append(line)
            i += 1

    return "\n".join(output_lines)


def markdown_to_telegram_html(text: str) -> str:
    """
    Transforms arbitrary Markdown into clean, safe Telegram HTML.
    Supports:
    - Code blocks: ```lang ... ``` -> <pre><code class="language-lang">...</code></pre>
    - Inline code: `code` -> <code>code</code>
    - Tables -> Structured Telegram cards
    - Headers: # / ## / ### / #### -> <b>Header</b>
    - Dividers: --- / *** / ___ -> clean separator
    - Bullets: * / - -> •
    - Bold: **text** / __text__ -> <b>text</b>
    - Italic: *text* / _text_ (safe against snake_case identifiers) -> <i>text</i>
    - Strikethrough: ~~text~~ -> <s>text</s>
    - Spoilers: ||text|| -> <tg-spoiler>text</tg-spoiler>
    - Links: [label](url) -> <a href="url">label</a>
    - Blockquotes: > quote -> <blockquote>quote</blockquote>
    - Escapes all raw <, >, & outside of tags.
    """
    if not text:
        return ""

    tokens: Dict[str, str] = {}
    token_counter = 0

    # 1. Extract and preserve fenced code blocks: ```lang\ncode\n```
    def replace_code_block(match: re.Match) -> str:
        nonlocal token_counter
        lang = (match.group(1) or "").strip().lower()
        code = match.group(2)
        if code.startswith("\n"):
            code = code[1:]
        if code.endswith("\n"):
            code = code[:-1]
        escaped_code = html.escape(code)
        if lang:
            replacement = f'<pre><code class="language-{html.escape(lang)}">{escaped_code}</code></pre>'
        else:
            replacement = f'<pre>{escaped_code}</pre>'
        token = f"\x00CB_{token_counter}\x00"
        token_counter += 1
        tokens[token] = replacement
        return token

    text = re.sub(r"```([a-zA-Z0-9_\+\-]*)\r?\n?(.*?)```", replace_code_block, text, flags=re.DOTALL)

    # 2. Convert markdown tables (may generate backticks for commands)
    text = convert_markdown_tables(text)

    # 3. Extract and preserve inline code: `code`
    def replace_inline_code(match: re.Match) -> str:
        nonlocal token_counter
        code = match.group(1)
        escaped_code = html.escape(code)
        replacement = f"<code>{escaped_code}</code>"
        token = f"\x00IC_{token_counter}\x00"
        token_counter += 1
        tokens[token] = replacement
        return token

    text = re.sub(r"`([^`\r\n]+)`", replace_inline_code, text)

    # 4. Convert Markdown headers (### Header -> **Header**)
    text = re.sub(r"^(#{1,6})\s+(.+)$", r"**\2**", text, flags=re.MULTILINE)

    # 5. Convert horizontal rules (---, ***, ___) -> clean divider
    text = re.sub(r"^\s*([*\-_])(\s*\1){2,}\s*$", r"— — — — — — — — — —", text, flags=re.MULTILINE)

    # 6. Convert bullet lists (* item, - item) -> • item
    text = re.sub(r"^(\s*)[*\-]\s+(.+)$", r"\1• \2", text, flags=re.MULTILINE)

    # 7. Escape HTML in all remaining plain text (<, >, &)
    text = html.escape(text)

    # 8. Convert Blockquotes (> quote) - note > is &gt; after escaping
    text = re.sub(r"^&gt;\s?(.*)$", r"<blockquote>\1</blockquote>", text, flags=re.MULTILINE)

    # 9. Convert Markdown styling to HTML tags
    # Bold: **text** or __text__ (non-newline spanning to avoid cross-line/glob collision)
    text = re.sub(r"\*\*(?!\s)([^\*\n]+?)(?<!\s)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)__(?!\s)([^_\n]+?)(?<!\s)__(?!\w)", r"<b>\1</b>", text)

    # Italic: *text* (excluding bold asterisks and globs)
    text = re.sub(r"(?<!\*)\*(?!\s|\*)([^\*\n]+?)(?<!\s|\*)\*(?!\*)", r"<i>\1</i>", text)
    # Italic: _text_ (require word boundary so snake_case like agent_manager is NOT touched)
    text = re.sub(r"(?<!\w)_(?!\s|_)([^_\n]+?)(?<!\s|_)_(?!\w)", r"<i>\1</i>", text)

    # Strikethrough: ~~text~~
    text = re.sub(r"~~(?!\s)([^~\n]+?)(?<!\s)~~", r"<s>\1</s>", text)

    # Spoilers: ||text||
    text = re.sub(r"\|\|(?!\s)([^\|\n]+?)(?<!\s)\|\|", r"<tg-spoiler>\1</tg-spoiler>", text)

    # Links: [text](https://...)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s\)]+)\)",
        r'<a href="\2">\1</a>',
        text
    )

    # 10. Reinsert preserved code blocks and inline code
    for token, replacement in tokens.items():
        text = text.replace(token, replacement)

    return text


def strip_html_tags(text: str) -> str:
    """Strips HTML tags and unescapes entities for plain-text fallback."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return html.unescape(clean)


def _get_open_tags(chunk: str) -> List[Tuple[str, str]]:
    """
    Inspects a chunk of HTML and returns a list of currently open tags
    as tuples of (tag_name, full_opening_tag), e.g. ('code', '<code class="language-python">').
    """
    tag_pattern = re.compile(r"<(/)?([a-zA-Z0-9_\-]+)(?:\s+[^>]*)?>")
    stack: List[Tuple[str, str]] = []

    # Void/self-closing tags that do not require closing
    void_tags = {"br", "hr", "img"}

    for match in tag_pattern.finditer(chunk):
        is_closing = bool(match.group(1))
        tag_name = match.group(2).lower()
        full_tag = match.group(0)

        if tag_name in void_tags:
            continue

        if is_closing:
            # Find and pop matching tag from top of stack
            for idx in range(len(stack) - 1, -1, -1):
                if stack[idx][0] == tag_name:
                    stack.pop(idx)
                    break
        else:
            stack.append((tag_name, full_tag))

    return stack


def split_telegram_message(html_text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> List[str]:
    """
    Splits long HTML messages into chunks <= max_length while safely:
    - Splitting at paragraph (\\n\\n) or line (\\n) boundaries.
    - Closing any open HTML tags at the end of a chunk.
    - Re-opening those tags at the start of the next chunk.
    """
    if len(html_text) <= max_length:
        return [html_text]

    chunks: List[str] = []
    remaining = html_text

    while len(remaining) > max_length:
        # Find best split point within max_length
        split_idx = -1
        window = remaining[:max_length]

        # 1. Prefer paragraph boundary
        p_idx = window.rfind("\n\n")
        if p_idx > max_length // 3:
            split_idx = p_idx + 2
        else:
            # 2. Prefer line boundary
            l_idx = window.rfind("\n")
            if l_idx > max_length // 3:
                split_idx = l_idx + 1
            else:
                # 3. Prefer space
                s_idx = window.rfind(" ")
                if s_idx > max_length // 3:
                    split_idx = s_idx + 1
                else:
                    split_idx = max_length

        current_chunk = remaining[:split_idx].rstrip()
        remaining = remaining[split_idx:].lstrip("\r\n")

        # Check for unclosed tags in current_chunk
        open_tags = _get_open_tags(current_chunk)
        if open_tags:
            # Close them on current_chunk in reverse order
            closing_tags = "".join(f"</{t[0]}>" for t in reversed(open_tags))
            current_chunk += closing_tags

            # Prepend reopening tags to remaining text
            reopen_tags = "".join(t[1] for t in open_tags)
            remaining = reopen_tags + remaining

        chunks.append(current_chunk)

    if remaining.strip():
        chunks.append(remaining)

    return chunks


async def send_formatted_reply(
    message: Message,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> List[Message]:
    """
    Converts Markdown to safe Telegram HTML, chunks if necessary, and sends
    via message.answer(). Falls back to plain text if Telegram rejects parsing.
    The reply_markup (if any) is attached to the final message chunk.
    """
    if not HAS_AIOGRAM or not message:
        return []

    html_text = markdown_to_telegram_html(text)
    chunks = split_telegram_message(html_text)
    sent_messages: List[Message] = []

    for idx, chunk in enumerate(chunks):
        is_last = (idx == len(chunks) - 1)
        markup = reply_markup if is_last else None

        try:
            sent = await message.answer(chunk, parse_mode=ParseMode.HTML, reply_markup=markup)
            sent_messages.append(sent)
        except Exception as e:
            logger.warning(f"Telegram HTML parse error: {e}. Falling back to plain text.")
            plain_chunk = strip_html_tags(chunk)
            try:
                sent = await message.answer(plain_chunk, parse_mode=None, reply_markup=markup)
                sent_messages.append(sent)
            except Exception as e2:
                logger.error(f"Failed to send plain text fallback: {e2}")

    return sent_messages


async def send_formatted_message(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> List[Message]:
    """
    Converts Markdown to safe Telegram HTML, chunks if necessary, and sends
    via bot.send_message(). Falls back to plain text if Telegram rejects parsing.
    The reply_markup (if any) is attached to the final message chunk.
    """
    if not HAS_AIOGRAM or not bot:
        return []

    html_text = markdown_to_telegram_html(text)
    chunks = split_telegram_message(html_text)
    sent_messages: List[Message] = []

    for idx, chunk in enumerate(chunks):
        is_last = (idx == len(chunks) - 1)
        markup = reply_markup if is_last else None

        try:
            sent = await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                reply_markup=markup
            )
            sent_messages.append(sent)
        except Exception as e:
            logger.warning(f"Telegram HTML parse error: {e}. Falling back to plain text.")
            plain_chunk = strip_html_tags(chunk)
            try:
                sent = await bot.send_message(
                    chat_id=chat_id,
                    text=plain_chunk,
                    parse_mode=None,
                    reply_markup=markup
                )
                sent_messages.append(sent)
            except Exception as e2:
                logger.error(f"Failed to send plain text fallback: {e2}")

    return sent_messages
