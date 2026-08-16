import subprocess
import tempfile
import sys
from pathlib import Path

def run_code(language, code, timeout=30):
    with tempfile.TemporaryDirectory() as d:
        if language == 'python':
            ext = '.py'
            cmd = [sys.executable, 'code.py']
        elif language == 'nim':
            ext = '.nim'
            cmd = ['nim', 'c', '-r', 'code.nim']
        elif language == 'zig':
            ext = '.zig'
            cmd = ['zig', 'run', 'code.zig']
        else:
            return {"success": False, "error": f"Unsupported language: {language}"}

        code_path = Path(d) / f"code{ext}"
        code_path.write_text(code)
        
        try:
            res = subprocess.run(
                cmd, 
                cwd=d, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "returncode": res.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
