import os
import re

svg_dir = 'svg'

for filename in os.listdir(svg_dir):
    if filename.endswith('.svg'):
        filepath = os.path.join(svg_dir, filename)
        with open(filepath, 'r') as f:
            content = f.read()
        
        content = re.sub(r'stroke="#[0-9a-fA-F]+"', 'stroke="currentColor"', content)
        content = re.sub(r'fill="#[0-9a-fA-F]+"', 'fill="none"', content)
        
        with open(filepath, 'w') as f:
            f.write(content)

print("SVG colors fixed!")