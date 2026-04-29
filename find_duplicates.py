import re
content = open(r'E:\jsjzy\pyqt_app\main.py', 'r', encoding='utf-8', errors='replace').read()
pattern = r'self\.table\.setItem\(i, 5, QTableWidgetItem\("-"\)\)'
matches = [(m.start(), m.end()) for m in re.finditer(pattern, content)]
print('found', len(matches))
for i, (s, e) in enumerate(matches):
    print(i)
    print(repr(content[s-300:e+100]))
    print('---')