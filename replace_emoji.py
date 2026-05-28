import re

emoji_map = {
    '🏷': 'Tag',
    '💬': 'Message square',
    '📄': 'File text',
    '📝': 'Edit',
    '🖼': 'Image',
    '🎬': 'Film',
    '🎵': 'Music',
    '📦': 'Package',
    '📊': 'Bar chart 2',
    '📈': 'Trending up',
    '📎': 'Paperclip',
    '📋': 'Clipboard',
    '📚': 'Book',
    '💡': 'Zap',
    '📅': 'Calendar',
    '☐': 'Square',
    '✏️': 'Edit',
    '✅': 'Check circle',
    '❌': 'X',
    '🔍': 'Search',
    '➕': 'Plus',
    '➖': 'Minus',
}

# 检查可用的 SVG 文件
import os
svg_dir = '/Volumes/Work-Project/SnapDoc/svg'
available_svgs = set()
for f in os.listdir(svg_dir):
    if f.endswith('.svg'):
        available_svgs.add(f[:-4])

content = open('/Volumes/Work-Project/SnapDoc/index.html').read()

for emoji, svg_name in emoji_map.items():
    possible_names = [svg_name, svg_name.replace(' ', '-'), svg_name.replace(' ', '')]
    found = False
    for name in possible_names:
        if name in available_svgs:
            replacement = f'<img src="svg/{name}.svg" class="emoji-svg">'
            content = content.replace(emoji, replacement)
            found = True
            print(f'Replaced {repr(emoji)} with svg/{name}.svg')
            break
    if not found:
        print(f'Warning: No SVG found for {repr(emoji)} ({svg_name})')

open('/Volumes/Work-Project/SnapDoc/index.html', 'w').write(content)
print('Done')