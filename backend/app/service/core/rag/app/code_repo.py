import ast
import copy
import os
import re
from pathlib import Path

from service.core.rag.nlp import find_codec, rag_tokenizer, tokenize
from service.core.rag.utils import num_tokens_from_string

MAX_FILE_BYTES = 1024 * 1024
MAX_BLOCK_TOKENS = 320
BLOCK_WINDOW_LINES = 120
BLOCK_WINDOW_OVERLAP = 30


CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".php",
    ".sh",
    ".bash",
    ".zsh",
    ".cs",
    ".kt",
    ".sql",
}
DOC_EXTENSIONS = {".md", ".markdown", ".rst", ".txt"}
CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env"}
SUPPORTED_EXTENSIONS = CODE_EXTENSIONS | DOC_EXTENSIONS | CONFIG_EXTENSIONS
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".venv",
    "venv",
    "target",
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".php": "php",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".sql": "sql",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "rst",
    ".txt": "text",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "config",
    ".conf": "config",
    ".env": "config",
}

SPECIAL_FILE_METADATA = {
    ".env": ("config", "config"),
    ".gitignore": ("config", "config"),
    ".dockerignore": ("config", "config"),
    ".editorconfig": ("config", "config"),
    "dockerfile": ("code", "docker"),
    "makefile": ("code", "makefile"),
    "readme": ("doc", "markdown"),
    "license": ("doc", "text"),
    "changelog": ("doc", "markdown"),
    "contributing": ("doc", "markdown"),
}

GENERIC_SYMBOL_PATTERNS = [
    (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][\w$]*)\s*\("), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][\w$]*)\s*=\s*(?:async\s*)?\("), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][\w$]*)\s*=\s*(?:async\s*)?[A-Za-z_][\w$<>\[\]]*\s*=>"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?(?:class|interface|enum|type)\s+([A-Za-z_][\w$]*)"), "class"),
    (re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][\w]*)\s*\("), "function"),
    (re.compile(r"^\s*([A-Za-z_][\w]*)\s*\(\)\s*\{"), "function"),
    (re.compile(r"^\s*(?:public|private|protected|internal|static|final|virtual|override|async|\s)+[\w<>\[\],\s]+\s+([A-Za-z_][\w$]*)\s*\([^;]*\)\s*\{"), "function"),
    (re.compile(r"^\s*(?:CREATE|ALTER)\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE|VIEW|TABLE)\s+([A-Za-z_][\w$\.]*)", re.IGNORECASE), "definition"),
]


def chunk(path, binary=None, callback=None, **kwargs):
    files, root = _collect_supported_files(path)
    results = []
    total = max(len(files), 1)

    for idx, file_path in enumerate(files, start=1):
        rel_path = os.path.relpath(file_path, root) if root else os.path.basename(file_path)
        if callback:
            callback(idx / total, f"Parsing {rel_path}")
        results.extend(_chunk_single_file(file_path, rel_path, binary if len(files) == 1 else None))

    return results


def supports_path(path):
    return os.path.isdir(path) or _is_supported_file(path)


def _collect_supported_files(path):
    if os.path.isdir(path):
        files = []
        for root, dirs, names in os.walk(path):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]
            for name in names:
                file_path = os.path.join(root, name)
                if _is_supported_file(file_path):
                    files.append(file_path)
        return sorted(files), path

    return ([path] if _is_supported_file(path) else []), os.path.dirname(path) or None


def _is_supported_file(path):
    return _classify_file(path) is not None


def _classify_file(path):
    file_name = Path(path).name.lower()
    if file_name in SPECIAL_FILE_METADATA:
        return SPECIAL_FILE_METADATA[file_name]
    if file_name.startswith(".env."):
        return "config", "config"

    suffix = Path(path).suffix.lower()
    if suffix in CODE_EXTENSIONS:
        return "code", LANGUAGE_BY_EXTENSION.get(suffix, "text")
    if suffix in DOC_EXTENSIONS:
        return "doc", LANGUAGE_BY_EXTENSION.get(suffix, "text")
    if suffix in CONFIG_EXTENSIONS:
        return "config", LANGUAGE_BY_EXTENSION.get(suffix, "config")
    return None


def _chunk_single_file(file_path, rel_path, binary=None):
    text = _read_text(file_path, binary)
    if not text.strip():
        return []

    file_class = _classify_file(file_path)
    if not file_class:
        return []
    file_type, language = file_class
    doc = _build_doc(rel_path, language)

    if language == "python":
        blocks = _extract_python_blocks(text)
    elif file_type == "doc":
        blocks = _extract_markdown_blocks(text, Path(rel_path).stem or rel_path)
    elif file_type == "config":
        blocks = _extract_config_blocks(text)
    else:
        blocks = _extract_generic_code_blocks(text)

    if not blocks:
        blocks = [_make_fallback_block(text.splitlines(), "module", Path(rel_path).stem or rel_path, 1)]

    normalized_blocks = _normalize_blocks(blocks)
    return [_build_chunk(doc, block) for block in normalized_blocks if block["content"].strip()]


def _read_text(file_path, binary=None):
    if binary is not None:
        blob = binary
    else:
        with open(file_path, "rb") as file:
            blob = file.read()

    if len(blob) > MAX_FILE_BYTES or b"\x00" in blob[:1024]:
        return ""
    encoding = find_codec(blob)
    return blob.decode(encoding or "utf-8", errors="ignore")


def _build_doc(rel_path, language):
    title_source = f"{rel_path} {Path(rel_path).stem}"
    title_tks = rag_tokenizer.tokenize(title_source)
    title_sm_tks = rag_tokenizer.fine_grained_tokenize(title_tks)
    file_path_tks = _tokenize_code_term(rel_path)
    file_path_sm_tks = rag_tokenizer.fine_grained_tokenize(file_path_tks) if file_path_tks else ""
    return {
        "docnm_kwd": rel_path,
        "title_tks": title_tks,
        "title_sm_tks": title_sm_tks,
        "file_path_kwd": rel_path,
        "file_path_tks": file_path_tks,
        "file_path_sm_tks": file_path_sm_tks,
        "language_kwd": language,
        "available_int": 1,
    }


def _build_chunk(doc, block):
    d = copy.deepcopy(doc)
    tokenize(d, block["content"], True)
    symbol = block.get("symbol", "")
    symbol_tks = _tokenize_code_term(symbol) if symbol else ""
    symbol_sm_tks = rag_tokenizer.fine_grained_tokenize(symbol_tks) if symbol_tks else ""
    chunk_kind = block.get("kind", "module")
    chunk_kind_tks = _tokenize_code_term(chunk_kind)
    d.update({
        "chunk_kind_kwd": chunk_kind,
        "chunk_kind_tks": chunk_kind_tks,
        "symbol_kwd": symbol,
        "symbol_tks": symbol_tks,
        "symbol_sm_tks": symbol_sm_tks,
        "start_line_int": block.get("start_line", 1),
        "end_line_int": block.get("end_line", 1),
    })
    return d


def _extract_python_blocks(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _extract_window_blocks(text.splitlines(), "module", "")

    lines = text.splitlines()
    blocks = []
    covered = []

    def visit_body(body, prefix=""):
        for node in body:
            if isinstance(node, ast.ClassDef):
                symbol = f"{prefix}.{node.name}" if prefix else node.name
                blocks.append(_make_ast_block(lines, node, "class", symbol))
                covered.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
                visit_body(node.body, symbol)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if prefix else "function"
                symbol = f"{prefix}.{node.name}" if prefix else node.name
                blocks.append(_make_ast_block(lines, node, kind, symbol))
                covered.append((node.lineno, getattr(node, "end_lineno", node.lineno)))

    visit_body(tree.body)
    blocks.extend(_extract_remaining_blocks(lines, covered))
    return sorted(blocks, key=lambda item: item["start_line"])


def _make_ast_block(lines, node, kind, symbol):
    start = max(node.lineno, 1)
    end = max(getattr(node, "end_lineno", start), start)
    return {
        "kind": kind,
        "symbol": symbol,
        "start_line": start,
        "end_line": end,
        "content": "\n".join(lines[start - 1:end]).strip(),
    }


def _extract_generic_code_blocks(text):
    lines = text.splitlines()
    blocks = []
    used_ranges = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        match = None
        kind = "module"
        for pattern, matched_kind in GENERIC_SYMBOL_PATTERNS:
            current = pattern.match(line)
            if current:
                match = current
                kind = matched_kind
                break
        if not match:
            idx += 1
            continue

        symbol = match.group(1)
        start_idx = idx
        end_idx = _find_block_end(lines, idx)
        used_ranges.append((start_idx + 1, end_idx + 1))
        blocks.append({
            "kind": kind,
            "symbol": symbol,
            "start_line": start_idx + 1,
            "end_line": end_idx + 1,
            "content": "\n".join(lines[start_idx:end_idx + 1]).strip(),
        })
        idx = end_idx + 1

    blocks.extend(_extract_remaining_blocks(lines, used_ranges))
    return sorted(blocks, key=lambda item: item["start_line"])


def _find_block_end(lines, start_idx):
    brace_balance = 0
    seen_brace = False
    idx = start_idx

    while idx < len(lines):
        line = lines[idx]
        brace_balance += line.count("{") - line.count("}")
        if "{" in line:
            seen_brace = True
        if seen_brace and brace_balance <= 0 and idx > start_idx:
            return idx
        if not seen_brace and idx > start_idx and not line.strip():
            return idx - 1
        idx += 1

    return len(lines) - 1


def _extract_markdown_blocks(text, fallback_symbol=""):
    lines = text.splitlines()
    headings = []
    for idx, line in enumerate(lines, start=1):
        if re.match(r"^\s{0,3}#{1,6}\s+", line):
            headings.append((idx, re.sub(r"^\s{0,3}#{1,6}\s+", "", line).strip()))

    if not headings:
        return _extract_window_blocks(lines, "doc_section", fallback_symbol)

    blocks = []
    if headings[0][0] > 1:
        preface = "\n".join(lines[:headings[0][0] - 1]).strip()
        if preface:
            blocks.append({
                "kind": "doc_section",
                "symbol": fallback_symbol or "Introduction",
                "start_line": 1,
                "end_line": headings[0][0] - 1,
                "content": preface,
            })

    for index, (start_line, title) in enumerate(headings):
        next_line = headings[index + 1][0] - 1 if index + 1 < len(headings) else len(lines)
        content = "\n".join(lines[start_line - 1:next_line]).strip()
        if not content:
            continue
        blocks.append({
            "kind": "doc_section",
            "symbol": title,
            "start_line": start_line,
            "end_line": next_line,
            "content": content,
        })
    return blocks


def _extract_config_blocks(text):
    lines = text.splitlines()
    blocks = []
    current_start = 1
    current_symbol = ""
    bucket = []

    for idx, line in enumerate(lines, start=1):
        if re.match(r"^\s*\[[^\]]+\]\s*$", line) or re.match(r"^\s*[A-Za-z0-9_.-]+\s*:\s*$", line):
            if bucket:
                blocks.append({
                    "kind": "config_section",
                    "symbol": current_symbol,
                    "start_line": current_start,
                    "end_line": idx - 1,
                    "content": "\n".join(bucket).strip(),
                })
            current_start = idx
            current_symbol = line.strip().strip("[]")
            bucket = [line]
            continue
        bucket.append(line)

    if bucket:
        blocks.append({
            "kind": "config_section",
            "symbol": current_symbol,
            "start_line": current_start,
            "end_line": len(lines),
            "content": "\n".join(bucket).strip(),
        })

    return [block for block in blocks if block["content"]]


def _normalize_blocks(blocks):
    normalized = []
    for block in blocks:
        normalized.extend(_split_large_block(block))
    return normalized


def _split_large_block(block):
    content = block.get("content", "")
    if not content:
        return []
    if num_tokens_from_string(content) <= MAX_BLOCK_TOKENS:
        return [block]

    lines = content.splitlines()
    if len(lines) <= BLOCK_WINDOW_LINES:
        return [block]

    return _extract_window_blocks(
        lines,
        block.get("kind", "module"),
        block.get("symbol", ""),
        start_line=block.get("start_line", 1),
        window_size=BLOCK_WINDOW_LINES,
        overlap=BLOCK_WINDOW_OVERLAP,
    )


def _extract_remaining_blocks(lines, covered_ranges):
    if not lines:
        return []

    coverage = [False] * len(lines)
    for start, end in covered_ranges:
        for idx in range(max(start - 1, 0), min(end, len(lines))):
            coverage[idx] = True

    blocks = []
    current_start = None
    current_lines = []
    for idx, (line, is_covered) in enumerate(zip(lines, coverage), start=1):
        if is_covered:
            if current_lines:
                blocks.extend(_flush_remaining_block(current_lines, current_start))
                current_lines = []
                current_start = None
            continue
        if current_start is None:
            current_start = idx
        current_lines.append(line)

    if current_lines:
        blocks.extend(_flush_remaining_block(current_lines, current_start))
    return blocks


def _flush_remaining_block(lines, start_line):
    if not "\n".join(lines).strip():
        return []
    return _extract_window_blocks(lines, "module", "", start_line=start_line)


def _extract_window_blocks(lines, kind, symbol, start_line=1, window_size=80, overlap=20):
    blocks = []
    idx = 0
    step = max(window_size - overlap, 1)
    while idx < len(lines):
        window = lines[idx:idx + window_size]
        if "\n".join(window).strip():
            blocks.append({
                "kind": kind,
                "symbol": symbol,
                "start_line": start_line + idx,
                "end_line": start_line + idx + len(window) - 1,
                "content": "\n".join(window).strip(),
            })
        idx += step
    return blocks


def _make_fallback_block(lines, kind, symbol, start_line):
    content = "\n".join(lines).strip()
    return {
        "kind": kind,
        "symbol": symbol,
        "start_line": start_line,
        "end_line": start_line + max(len(lines) - 1, 0),
        "content": content,
    }


def _tokenize_code_term(value):
    if not value:
        return ""
    parts = re.split(r"[\\/._:\-\s]+", value)
    expanded = []
    for part in parts:
        if not part:
            continue
        expanded.append(part)
        expanded.extend(_split_identifier(part))
    normalized = " ".join(dict.fromkeys(piece.lower() for piece in expanded if piece))
    if not normalized:
        return ""
    return rag_tokenizer.tokenize(normalized)


def _split_identifier(value):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return re.split(r"[^A-Za-z0-9]+", value)
