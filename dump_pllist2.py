content=open(r'E:\jsjzy\pyqt_app\main.py','r',encoding='utf-8',errors='replace').read()
idx=content.find('def ncm_get_playlists')
with open(r'E:\jsjzy\pyqt_app\dump_pllist.txt','w',encoding='utf-8') as f:
    f.write(content[idx:idx+800])