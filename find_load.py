content=open(r'E:\jsjzy\pyqt_app\main.py','r',encoding='utf-8',errors='replace').read()
idx=content.find('def load_playlist')
print(content[idx:idx+1200])