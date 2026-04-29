content=open(r'E:\jsjzy\pyqt_app\main.py','r',encoding='utf-8',errors='replace').read()
idx=content.find('def run_ncm_global')
with open(r'E:\jsjzy\pyqt_app\run_ncm.txt','w',encoding='utf-8') as f:
    f.write(content[idx:idx+600])