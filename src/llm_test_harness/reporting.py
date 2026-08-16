import json
from jinja2 import Template

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
body { font-family: sans-serif; margin: 20px; background: #fafafa; }
.test { background: white; border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
.pass { border-left: 5px solid #28a745; }
.fail { border-left: 5px solid #dc3545; }
pre { background: #f4f4f4; padding: 10px; overflow-x: auto; border-radius: 4px; }
.eval-pass { color: #28a745; font-weight: bold; }
.eval-fail { color: #dc3545; font-weight: bold; }
.meta { color: #666; font-size: 0.9em; margin-bottom: 10px; }
.metrics-list { list-style-type: none; padding: 0; margin: 5px 0 15px 0; display: flex; flex-wrap: wrap; gap: 15px; }
.metrics-list li { background: #e9ecef; padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 0.85em; }
</style>
</head>
<body>
<h1>LLM Test Harness Report</h1>
<p>Run ID: {{ run_id }}</p>
<p>Total: {{ results|length }} | Pass: {{ pass_count }} | Fail: {{ fail_count }}</p>

{% for r in results %}
<div class="test {{ r.status }}">
    <h3>{{ r.test_id }} <span class="meta">({{ r.model }})</span></h3>
    <p class="meta">Category: {{ r.category }} / {{ r.subcategory }} | Status: <strong>{{ r.status|upper }}</strong> | Attempts: {{ r.attempts }}</p>
    
    <h4>Performance Metrics:</h4>
    <ul class="metrics-list">
        <li>Total Latency: <strong>{{ r.metrics.get('latency_ms', 'N/A') }} ms</strong></li>
        <li>Prompt Tokens: <strong>{{ r.metrics.get('prompt_tokens', 'N/A') }}</strong></li>
        <li>Completion Tokens: <strong>{{ r.metrics.get('completion_tokens', 'N/A') }}</strong></li>
        {% if r.metrics.get('prompt_time_ms') %}
        <li>Time to First Token / Prompt Eval: <strong>{{ r.metrics.get('prompt_time_ms') }} ms</strong></li>
        {% endif %}
        {% if r.metrics.get('completion_time_ms') %}
        <li>Generation Time: <strong>{{ r.metrics.get('completion_time_ms') }} ms</strong></li>
        {% endif %}
        {% if r.metrics.get('tokens_per_second') %}
        <li>Tokens per Second (TPS): <strong>{{ r.metrics.get('tokens_per_second') }}</strong></li>
        {% endif %}
    </ul>
    
    <h4>Initial Prompt:</h4>
    <pre>{{ r.request.messages[0].content if r.request.messages else '' }}</pre>
    
    {% if r.attempts > 1 %}
    <h4>Retries: {{ r.attempts - 1 }}</h4>
    {% endif %}
    
    <h4>Response:</h4>
    <pre>{{ r.response.content }}</pre>
    
    {% if r.response.extracted %}
    <h4>Extracted JSON:</h4>
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

    <h4>Human Review:</h4>
    <p>Score: {{ r.human_score | default('N/A') }} | Notes: {{ r.human_notes | default('') }}</p>
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
