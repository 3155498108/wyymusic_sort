content=open(r'E:\jsjzy\pyqt_app\main.py','r',encoding='utf-8',errors='replace').read()
idx=content.find('for wt in web_tracks:')
with open(r'E:\jsjzy\pyqt_app\ncm_snippet.txt','w',encoding='utf-8') as f:
    f.write(content[idx:idx+500])