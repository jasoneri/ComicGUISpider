#!/usr/bin/python
# -*- coding: utf-8 -*-
import markdown
from utils import ori_path


with open(ori_path.joinpath('assets/github_format.html'), 'r', encoding='utf-8') as f:
    github_markdown_format = f.read()


class MarkdownConverter:
    github_markdown_format = github_markdown_format
    md = markdown.Markdown(extensions=['markdown.extensions.md_in_html', 
        'markdown.extensions.tables', 'markdown.extensions.fenced_code', 'markdown.extensions.nl2br',
        'markdown.extensions.admonition'],
        output_format='html5')

    @classmethod
    def convert_html(cls, md_content):
        html_body = cls.md.convert(md_content)
        full_html = cls.github_markdown_format.replace('{content}', html_body)
        return full_html

    @classmethod
    def transfer_markdown(cls, _in, _out):
        with open(_in, 'r', encoding='utf-8') as f:
            _md_content = f.read()
        _html = cls.convert_html(_md_content)
        with open(_out, 'w', encoding='utf-8') as f:
            f.write(_html)


class MdHtml(str):
    def cdn_replace(self, author, repo, branch):
        return MdHtml(self.replace("raw.githubusercontent.com", "jsd.vxo.im/gh")
                .replace(f"{author}/{repo}/{branch}", f"{author}/{repo}@{branch}"))

    @property
    def details_formatter(self):
        # before MarkdownConverter.convert_html()
        return MdHtml(self.replace("<details>", '<details markdown="1">'))
