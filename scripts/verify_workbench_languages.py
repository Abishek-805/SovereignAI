"""Run small language fixtures only in the verified Docker sandbox."""
import json
import time
from pathlib import Path
from router.sandbox import CodeSandbox
from workflows.code_runtime import runner

CASES = {
 'main.py': 'print(42)',
 'src/main.js': 'console.log(42)',
 'main.ts': 'const n:number=42; console.log(n);',
 'Main.java': 'public class Main { public static void main(String[] args) { System.out.println(42); }}',
 'main.c': '#include <stdio.h>\nint main(){printf("42\\n");return 0;}',
 'main.cpp': '#include <iostream>\nint main(){std::cout<<42;}',
 'main.go': 'package main\nimport "fmt"\nfunc main(){fmt.Println(42)}',
 'main.rs': 'fn main(){println!("42");}',
 'main.php': '<?php echo 42;', 'main.rb': 'puts 42', 'main.sh': 'echo 42',
 'main.sql': 'CREATE TABLE numbers (n INTEGER); INSERT INTO numbers VALUES (42);',
}

def main():
 root=Path(__file__).resolve().parents[1]
 image=json.loads((root/'data/sandbox-validation.json').read_text())['image_id']
 sandbox=CodeSandbox('docker',image)
 results={}
 for name,content in CASES.items():
  started=time.perf_counter()
  result=sandbox.execute(runner(name,'run'),input_files={name:content.encode()})
  passed=result.executed and result.exit_code==0 and ('42' in result.stdout or name.endswith('.sql'))
  results[name]={'passed':passed,'exit_code':result.exit_code,'executed':result.executed,'stdout':result.stdout,'stderr':result.stderr,'seconds':round(time.perf_counter()-started,2),'image_id':image}
  print(name,passed,flush=True)
 (root/'benchmarks/workbench-language-matrix.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
 return all(item['passed'] for item in results.values())

if __name__=='__main__': raise SystemExit(0 if main() else 1)
