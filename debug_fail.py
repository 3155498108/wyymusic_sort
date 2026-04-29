import subprocess, os, sys

print(f"MEIPASS: {getattr(sys, '_MEIPASS', 'NOT SET')}")
print(f"CWD: {os.getcwd()}")
print(f"os.path.exists('C:\\Program Files\\nodejs\\npm.cmd'): {os.path.exists(r'C:\Program Files\nodejs\npm.cmd')}")

npm = r"C:\Program Files\nodejs\npm.cmd"
cmd = [npm, "exec", "--global", "ncm-cli", "--", "--version"]

env = {**os.environ, "USERPROFILE": os.path.expanduser("~"), "HOME": os.path.expanduser("~")}
try:
    r = subprocess.run(cmd, capture_output=True, timeout=15, env=env)
    print(f"rc={r.returncode}")
    print(f"stdout: {r.stdout.decode().strip()}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
