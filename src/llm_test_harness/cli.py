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
from .evaluators import evaluate

def main():
    console = Console()
    parser = argparse.ArgumentParser(description="LLM Test Harness")
    subparsers = parser.add_subparsers(dest="cmd")
    
    run_p = subparsers.add_parser("run")
    run_p.add_argument("--endpoint", default="http://localhost:5000")
    run_p.add_argument("--model", default="*")
    run_p.add_argument("--suite", default="suites")
    run_p.add_argument("--filter", default="*")
    run_p.add_argument("--category", help="Filter by category")
    run_p.add_argument("--subcategory", help="Filter by subcategory")
    run_p.add_argument("--timeout", type=float, default=300.0, help="Request timeout in seconds (default: 300)")
    run_p.add_argument("--judge-model", help="Model to use as judge for semantic evaluation")
    run_p.add_argument("--judge-endpoint", help="Endpoint for the judge model")
    
    report_p = subparsers.add_parser("report")
    report_p.add_argument("run_dir")
    
    eval_p = subparsers.add_parser("evaluate")
    eval_p.add_argument("run_dir", help="Directory containing the run to evaluate")
    eval_p.add_argument("--suite", default="suites", help="Directory containing test suites")
    eval_p.add_argument("--judge-model", help="Model to use as judge for semantic evaluation")
    eval_p.add_argument("--judge-endpoint", help="Endpoint for the judge model")
    eval_p.add_argument("--endpoint", default="http://localhost:5000", help="Default endpoint if judge endpoint is not specified")
    eval_p.add_argument("--timeout", type=float, default=300.0, help="Request timeout in seconds")

    args = parser.parse_args()
    
    if args.cmd == "run":
        client = LLMClient(args.endpoint, timeout=args.timeout)
        
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
        if args.category:
            tests = [t for t in tests if t.get('category') == args.category]
        if args.subcategory:
            tests = [t for t in tests if t.get('subcategory') == args.subcategory]
            
        if not tests:
            console.print("[yellow]No tests found matching criteria.[/yellow]")
            return

        run_dir = Path("runs") / datetime.now().strftime("%Y-%m-%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        for model in models:
            console.print(f"\n[bold blue]Testing model: {model}[/bold blue]")
            for test in tests:
                console.print(f"  Running {test['id']}...", end=" ")
                res = run_test(
                    client, model, test, run_dir, 
                    judge_model=args.judge_model, 
                    judge_endpoint=args.judge_endpoint
                )
                results.append(res)
                status = res.get('status', 'error')
                if status == 'pass':
                    console.print(f"[green]PASS[/green]")
                elif status == 'error':
                    console.print(f"[yellow]ERROR[/yellow]")
                    if res.get('error'):
                        console.print(f"    [dim]{res['error']}[/dim]")
                else:
                    console.print(f"[red]FAIL[/red]")
                    for ev in res.get('evaluations', []):
                        if not ev.get('passed'):
                            console.print(f"    [dim]{ev['type']}: {ev.get('details', 'failed')}[/dim]")
                
        generate_report(results, run_dir)
        console.print(f"\nReport saved to {run_dir / 'report.html'}")
        console.print(f"Edit {run_dir / 'results.json'} to add 'human_score' and 'human_notes', then run: llm-harness report {run_dir}")

    elif args.cmd == "report":
        run_dir = Path(args.run_dir)
        with open(run_dir / "results.json") as f:
            results = json.load(f)
        generate_report(results, run_dir)
        console.print(f"Report regenerated for {run_dir}")

    elif args.cmd == "evaluate":
        run_dir = Path(args.run_dir)
        results_path = run_dir / "results.json"
        if not results_path.exists():
            console.print(f"[red]Error: {results_path} not found.[/red]")
            return
            
        with open(results_path) as f:
            results = json.load(f)
            
        # Load tests to get evaluation definitions
        suite_dir = Path(args.suite)
        tests = []
        if suite_dir.exists():
            for p in suite_dir.rglob("*.yaml"):
                with open(p) as f:
                    tests.append(yaml.safe_load(f))
                    
        test_map = {t['id']: t for t in tests}
        
        # Setup clients
        client = LLMClient(args.endpoint, timeout=args.timeout)
        judge_client = None
        if args.judge_endpoint:
            judge_client = LLMClient(args.judge_endpoint, timeout=args.timeout)
            
        updated_count = 0
        for res in results:
            test_id = res.get('test_id')
            if test_id in test_map:
                test = test_map[test_id]
                eval_defs = test.get('evaluation', [])
                
                extracted = res.get('response', {}).get('extracted')
                raw_content = res.get('response', {}).get('content')
                
                if extracted is not None or raw_content is not None:
                    new_eval_results = evaluate(
                        eval_defs, 
                        extracted, 
                        raw_content, 
                        client=judge_client if judge_client else client, 
                        default_model=res.get('model'), 
                        judge_model=args.judge_model,
                        judge_endpoint=args.judge_endpoint
                    )
                    passed = all(er.get('passed', False) for er in new_eval_results)
                    res['evaluations'] = new_eval_results
                    res['status'] = "pass" if passed else "fail"
                    updated_count += 1
                    
        if updated_count > 0:
            generate_report(results, run_dir)
            console.print(f"Re-evaluated {updated_count} results and updated report at {run_dir / 'report.html'}")
        else:
            console.print("No results could be re-evaluated.")
