import argparse
import yaml
import json
import fnmatch
from pathlib import Path
from datetime import datetime
from rich.console import Console

from .client import LLMClient
from .runner import run_test
from .reporting import generate_report

console = Console()

def main():
    parser = argparse.ArgumentParser(description="LLM Test Harness")
    subparsers = parser.add_subparsers(dest="cmd")
    
    run_p = subparsers.add_parser("run")
    run_p.add_argument("--endpoint", default="http://localhost:5000/v1")
    run_p.add_argument("--model", default="*")
    run_p.add_argument("--suite", default="suites")
    run_p.add_argument("--filter", default="*")
    
    report_p = subparsers.add_parser("report")
    report_p.add_argument("run_dir")
    
    args = parser.parse_args()
    
    if args.cmd == "run":
        client = LLMClient(args.endpoint)
        
        models = client.get_models()
        if not models:
            console.print("[yellow]Could not auto-discover models. Using 'default' model name.[/yellow]")
            models = ["default"]
            
        if args.model != "*":
            models = [m for m in models if fnmatch.fnmatch(m, args.model)]
            
        if not models:
            console.print("[red]No models found matching filter.[/red]")
            return
            
        suite_dir = Path(args.suite)
        tests = []
        if suite_dir.exists():
            for p in suite_dir.rglob("*.yaml"):
                with open(p) as f:
                    tests.append(yaml.safe_load(f))
                
        if args.filter != "*":
            tests = [t for t in tests if fnmatch.fnmatch(t['id'], args.filter)]
            
        run_dir = Path("runs") / datetime.now().strftime("%Y-%m-%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        for model in models:
            console.print(f"\n[bold blue]Testing model: {model}[/bold blue]")
            for test in tests:
                console.print(f"  Running {test['id']}...", end=" ")
                res = run_test(client, model, test, run_dir)
                results.append(res)
                console.print(f"[green]PASS[/green]" if res['status'] == 'pass' else f"[red]FAIL[/red]")
                
        generate_report(results, run_dir)
        console.print(f"\nReport saved to {run_dir / 'report.html'}")
        console.print(f"Edit {run_dir / 'results.json'} to add 'human_score' and 'human_notes', then run: llm-harness report {run_dir}")

    elif args.cmd == "report":
        run_dir = Path(args.run_dir)
        with open(run_dir / "results.json") as f:
            results = json.load(f)
        generate_report(results, run_dir)
        console.print(f"Report regenerated for {run_dir}")

if __name__ == "__main__":
    main()
