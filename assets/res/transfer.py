#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pathlib
import hashlib
from datetime import datetime
import yaml
import polib


def yaml_to_po(lang, yaml_file, po_file):
    with open(yaml_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    po = polib.POFile()
    po.metadata = {
        'Project-Id-Version': 'ComicGUISpider',
        'POT-Creation-Date': datetime.now().strftime('%Y-%m-%d %H:%M%z'),
        'Language': lang,
        'MIME-Version': '1.0',
        'Content-Type': 'text/plain; charset=utf-8',
        'Content-Transfer-Encoding': '8bit',
    }
    
    def process_dict(data, prefix=''):
        for key, value in data.items():
            entry_id = f"{prefix}{key}" if prefix else key
            if isinstance(value, dict):
                process_dict(value, f"{entry_id}.")
            else:
                entry = polib.POEntry(
                    msgid=entry_id,
                    msgstr=str(value),
                )
                po.append(entry)
    process_dict(data)
    po.save(po_file)
    
    return po

def compile_po_to_mo(po_file, mo_file):
    po = polib.pofile(po_file)
    po.save_as_mofile(mo_file)


def main(base_dir, lang):
    locale_dir = base_dir / 'locale' / lang / 'LC_MESSAGES'
    locale_dir.mkdir(parents=True, exist_ok=True)
    
    yaml_file = base_dir / 'locale' / f'{lang}.yml'
    yaml_hash = base_dir / 'locale' / f'{lang}.hash'
    po_file = base_dir / 'locale' / lang / 'LC_MESSAGES' / 'res.po'
    mo_file = base_dir / 'locale' / lang / 'LC_MESSAGES' / 'res.mo'
    
    po = yaml_to_po(lang, yaml_file, po_file)
    compile_po_to_mo(po_file, mo_file)
    with open(yaml_hash, 'w', encoding='utf-8') as f:
        f.write(hashlib.sha256(yaml_file.read_bytes()).hexdigest())


if __name__ == "__main__":
    main(pathlib.Path(__file__).parent, 'zh-CN') 
    main(pathlib.Path(__file__).parent, 'en-US') 
