import json
from jinja2 import Template

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<style>
body { font-family: sans-serif; margin: 20px; background: #fafafa; }
.test { background: white; border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
.pass { border-left: 5px solid #28a745; }
.fail { border-left: 5px solid #dc3545; }
.error { border-left: 5px solid #ffc107; }
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
<p>Total: {{ results|length }} | Pass: {{ pass_count }} | Fail: {{ fail_count }} | Error: {{ error_count }}</p>

{% for r in results %}
<div class="test {{ r.status }}">
    <h3>{{ r.test_id }} <span class="meta">({{ r.model }})</span></h3>
    <p class="meta">Category: {{ r.category | default('') }} / {{ r.subcategory | default('') }} | Status: <strong>{{ r.status|upper }}</strong> | Attempts: {{ r.attempts | default(0) }}</p>

    {% if r.status == 'error' %}
    <h4>Error:</h4>
    <pre>{{ r.error }}</pre>
    {% else %}

    <h4>Performance Metrics:</h4>
    <ul class="metrics-list">
        {% set metrics = r.metrics | default({}) %}
        <li>Total Latency: <strong>{{ metrics.get('latency_ms', 'N/A') }} ms</strong></li>
        <li>Prompt Tokens: <strong>{{ metrics.get('prompt_tokens', 'N/A') }}</strong></li>
        <li>Completion Tokens: <strong>{{ metrics.get('completion_tokens', 'N/A') }}</strong></li>
        {% if metrics.get('prompt_time_ms') %}
        <li>Time to First Token / Prompt Eval: <strong>{{ metrics.get('prompt_time_ms') }} ms</strong></li>
        {% endif %}
        {% if metrics.get('completion_time_ms') %}
        <li>Generation Time: <strong>{{ metrics.get('completion_time_ms') }} ms</strong></li>
        {% endif %}
        {% if metrics.get('tokens_per_second') %}
        <li>Tokens per Second (TPS): <strong>{{ metrics.get('tokens_per_second') }}</strong></li>
        {% endif %}
    </ul>

    <h4>Initial Prompt:</h4>
    {% set request = r.request | default({}) %}
    {% set messages = request.get('messages', []) %}
    <pre>{{ messages[0].content if messages else '' }}</pre>

    {% if r.attempts | default(1) > 1 %}
    <h4>Retries: {{ r.attempts - 1 }}</h4>
    {% endif %}

    <h4>Response:</h4>
    {% set response = r.response | default({}) %}
    <pre>{{ response.content | default('') }}</pre>

    {% if response.extracted %}
    <h4>Extracted JSON:</h4>
    <pre>{{ response.extracted | tojson(indent=2) }}</pre>
    {% endif %}

    {% if r.execution %}
    <h4>Execution Result:</h4>
    <pre>Success: {{ r.execution.success }}
Stdout: {{ r.execution.stdout }}
Stderr: {{ r.execution.stderr }}</pre>
    {% endif %}

    <h4>Evaluations:</h4>
    <ul>
    {% for e in r.evaluations | default([]) %}
        <li class="{{ 'eval-pass' if e.passed else 'eval-fail' }}">
            {{ e.type }}: {{ 'PASS' if e.passed else 'FAIL' }}
            {% if e.details %}<small>({{ e.details }})</small>{% endif %}
        </li>
    {% endfor %}
    </ul>
    {% endif %}

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
    error_count = sum(1 for r in results if r['status'] == 'error')

    template = Template(HTML_TEMPLATE)
    html = template.render(
        run_id=run_dir.name,
        results=results,
        pass_count=pass_count,
        fail_count=fail_count,
        error_count=error_count
    )

    (run_dir / "report.html").write_text(html)
    (run_dir / "results.json").write_text(json.dumps(results, indent=2))
