content=open(r'E:\jsjzy\pyqt_app\main.py','r',encoding='utf-8',errors='replace').read()
idx=content.find('def _on_select(self, row):')
with open(r'E:\jsjzy\pyqt_app\dump_onselect2.txt','w',encoding='utf-8') as f:
    f.write(content[idx:idx+600])