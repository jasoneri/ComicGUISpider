import re
import importlib
import inspect


class SearchKey(str):
    def __new__(cls, content, group_idx=0):
        instance = super().__new__(cls, content)
        instance.group_idx = group_idx
        return instance

    def __getnewargs__(self):
        """支持 pickle 序列化"""
        return (str(self), self.group_idx)


class Content:
    def __init__(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.raw_lines = content.split('\n')
        self.extracted = [line.strip() for line in self.raw_lines if line.strip()]
        self.line_map = {idx: line for idx, line in enumerate(self.extracted)}

    def remove_by_indices(self, indices):
        lines_to_remove = {self.line_map[idx] for idx in indices if idx in self.line_map}
        return [line for line in self.raw_lines if line.strip() not in lines_to_remove]


class Extractor:
    def __init__(self):
        self.file_path = None
        self.content_obj = None

    @staticmethod
    def get_available_methods():
        try:
            extractor_module = importlib.import_module('utils.ags.extractor')
            methods = [
                name for name, obj in inspect.getmembers(extractor_module, inspect.isfunction)
                if not name.startswith('_') and obj.__module__ == 'utils.ags.extractor'
            ]
            return sorted(methods)
        except ImportError as e:
            raise ValueError(f"Failed to import extractor module: {e}")

    def from_method(self, method_name, text):
        available_methods = self.get_available_methods()
        if method_name not in available_methods:
            raise ValueError(
                f"Method '{method_name}' not found. Available: {available_methods}"
            )
        extractor_module = importlib.import_module('utils.ags.extractor')
        func = getattr(extractor_module, method_name)
        return func(text)

    def change_file(self, file_path):
        self.file_path = file_path
        return self

    def load(self):
        if not self.file_path:
            raise ValueError("File path not set")
        return Content(self.file_path)

    def remove_list(self, book_list):
        if not self.file_path:
            return
        line_indices = [
            book.search_keyword.group_idx for book in book_list
            if hasattr(book, 'search_keyword') and hasattr(book.search_keyword, 'group_idx')
        ]
        if not line_indices:
            return
        content = Content(self.file_path)
        filtered_lines = content.remove_by_indices(line_indices)
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(filtered_lines))


def parse(item):
    cleaned = item.strip()
    if not cleaned:
        return ""
    # 去除前置标签
    parsed = re.sub(r'^(?:\([^)]+\))?\[[^\]]+\]', '', cleaned)
    if '|' in parsed:
        parsed = parsed.split('|')[0]
    # 去除所有括号和方括号
    parsed = re.sub(r'\[[^\]]+\]', '', parsed)
    parsed = re.sub(r'\([^)]+\)', '', parsed)
    parsed = re.sub(r'「[^」]*」', '', parsed)
    # 清理空白
    parsed = re.sub(r'\s+', ' ', parsed).strip()
    # 优先保留非中文部分
    parts = parsed.split()
    if len(parts) > 1:
        non_chinese_parts = []
        for part in parts:
            chinese_chars = sum(1 for c in part if '\u4e00' <= c <= '\u9fff')
            total_chars = len(part)
            if total_chars == 0 or chinese_chars / total_chars < 0.5:
                non_chinese_parts.append(part)
        if non_chinese_parts:
            parsed = ' '.join(non_chinese_parts)
    return parsed.strip()
