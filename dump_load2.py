content=open(r'E:\jsjzy\pyqt_app\main.py','r',encoding='utf-8',errors='replace').read()
idx=content.find('def _bg_load_tracks')
with open(r'E:\jsjzy\pyqt_app\load_snippet2.txt','w',encoding='utf-8') as f:
    f.write(content[idx:idx+1500])