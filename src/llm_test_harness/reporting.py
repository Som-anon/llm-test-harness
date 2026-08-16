import json
from pathlib import Path
from jinja2 import Template

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
body { font-family: sans-serif; margin: 20px; }
.test { border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; border-radius: 5px; }
.pass { border-left: 5px solid green; }
.fail { border-left: 5px solid red; }
pre { background: #f4f4f4; padding: 10px; overflow-x: auto; }
.eval-pass { color: green; font-weight: bold; }
.eval-fail { color: red; font-weight: bold; }
</style>
</head>
<body>
<h1>LLM Test Harness Report</h1>
<p>Run ID: {{ run_id }}</p>
<p>Total: {{ results|length }} | Pass: {{ pass_count }} | Fail: {{ fail_count }}</p>

{% for r in results %}
<div class="test {{ r.status }}">
    <h3>{{ r.test_id }} ({{ r.model }})</h3>
    <p>Status: <strong>{{ r.status|upper }}</strong> | Attempts: {{ r.attempts }} | Latency: {{ r.latency_ms }}ms</p>
    
    <h4>Initial Prompt:</h4>
    <pre>{{ r.request.messages[0].content if r.request.messages else '' }}</pre>
    
    {% if r.attempts > 1 %}
    <h4>Retries: {{ r.attempts - 1 }}</h4>
    {% endif %}
    
    <h4>Response:</h4>
    <pre>{{ r.response.content }}</pre>
    
    {% if r.response.extracted %}
    <h4>Extracted:</h4>
    <pre>{{ r.response.extracted | tojson(indent=2) }}</pre>
    {% endif %}
    
    {% if r.execution %}
    <h4>Execution Result:</h4>
    <pre>Success: {{ r.execution.success }}
Stdout: {{ r.execution.stdout }}
Stderr: {{ r.execution.stderr }}</pre>
    {% endif %}
    
    <h4>Evaluations:</h4>
    <ul>
    {% for e in r.evaluations %}
        <li class="{{ 'eval-pass' if e.passed else 'eval-fail' }}">
            {{ e.type }}: {{ 'PASS' if e.passed else 'FAIL' }} 
            {% if e.details %}<small>({{ e.details }})</small>{% endif %}
        </li>
    {% endfor %}
    </ul>

    {% if r.human_score is defined %}
    <h4>Human Review:</h4>
    <p>Score: {{ r.human_score }} | Notes: {{ r.human_notes }}</p>
    {% endif %}
</div>
{% endfor %}
</body>
</html>
"""

def generate_report(results, run_dir):
    pass_count = sum(1 for r in results if r['status'] == 'pass')
    fail_count = sum(1 for r in results if r['status'] == 'fail')
    
    template = Template(HTML_TEMPLATE)
    html = template.render(
        run_id=run_dir.name,
        results=results,
        pass_count=pass_count,
        fail_count=fail_count
    )
    
    (run_dir / "report.html").write_text(html)
    (run_dir / "results.json").write_text(json.dumps(results, indent=2))
