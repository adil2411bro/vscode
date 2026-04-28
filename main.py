import json
import os
import re
import urllib.error
import urllib.request

from flask import Flask, render_template_string, request

app = Flask(__name__)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDGLpHs792e1bc4c9vyi8SsPypVI1Mr8cQnpx")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
MODEL_CACHE = {"name": None}


PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Essay Checker</title>
    <style>
        :root {
            --bg: #f3efe6;
            --panel: #fffaf2;
            --ink: #1e293b;
            --muted: #64748b;
            --accent: #c26d3a;
            --accent-dark: #8f4d26;
            --line: #e7dccf;
            --good: #256c3f;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Georgia, "Times New Roman", serif;
            color: var(--ink);
            background:
                radial-gradient(circle at top left, rgba(194, 109, 58, 0.18), transparent 28%),
                linear-gradient(135deg, #f8f3eb 0%, #efe5d7 100%);
            min-height: 100vh;
        }

        .page {
            width: min(960px, calc(100% - 32px));
            margin: 32px auto;
        }

        .hero,
        .results {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: 0 16px 40px rgba(30, 41, 59, 0.08);
        }

        .hero {
            padding: 32px;
        }

        h1,
        h2,
        h3 {
            margin-top: 0;
        }

        h1 {
            font-size: clamp(2rem, 5vw, 3.4rem);
            margin-bottom: 12px;
        }

        p {
            line-height: 1.6;
        }

        .lead {
            max-width: 700px;
            color: var(--muted);
            margin-bottom: 24px;
        }

        form {
            display: grid;
            gap: 16px;
        }

        textarea {
            width: 100%;
            min-height: 320px;
            resize: vertical;
            border-radius: 16px;
            border: 1px solid #d7c6b3;
            padding: 18px;
            font: inherit;
            font-size: 1rem;
            background: #fffdf8;
            color: var(--ink);
        }

        textarea:focus {
            outline: 2px solid rgba(194, 109, 58, 0.25);
            border-color: var(--accent);
        }

        button {
            width: fit-content;
            border: 0;
            border-radius: 999px;
            padding: 14px 22px;
            font-size: 1rem;
            font-weight: 700;
            color: white;
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%);
            cursor: pointer;
        }

        button:hover {
            filter: brightness(1.03);
        }

        .results {
            margin-top: 24px;
            padding: 28px 32px;
        }

        .score {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            font-size: 1.2rem;
            font-weight: 700;
            color: var(--good);
            background: #edf7ef;
            border-radius: 999px;
            padding: 10px 16px;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 14px;
            margin: 20px 0 24px;
        }

        .card {
            padding: 16px;
            background: #fffdf8;
            border: 1px solid var(--line);
            border-radius: 14px;
        }

        .label {
            display: block;
            font-size: 0.9rem;
            color: var(--muted);
            margin-bottom: 6px;
        }

        ul {
            padding-left: 20px;
            line-height: 1.6;
        }

        .empty {
            color: #8a2d2d;
            font-weight: 700;
        }
    </style>
</head>
<body>
    <main class="page">
        <section class="hero">
            <h1>Student Essay Checker</h1>
            <p class="lead">
                Paste an essay below to get a Gemini-powered score and feedback on structure,
                argument quality, grammar, clarity, and overall writing effectiveness.
            </p>

            <form method="post">
                <label for="essay"><strong>Essay text</strong></label>
                <textarea id="essay" name="essay" placeholder="Paste the student's essay here...">{{ essay }}</textarea>
                <button type="submit">Check Essay</button>
            </form>

            {% if error %}
                <p class="empty">{{ error }}</p>
            {% endif %}
        </section>

        {% if result %}
            <section class="results">
                <h2>Evaluation Result</h2>
                <div class="score">Score: {{ result.score }}/100</div>

                <div class="grid">
                    <div class="card">
                        <span class="label">Word Count</span>
                        <strong>{{ result.word_count }}</strong>
                    </div>
                    <div class="card">
                        <span class="label">Sentences</span>
                        <strong>{{ result.sentence_count }}</strong>
                    </div>
                    <div class="card">
                        <span class="label">Paragraphs</span>
                        <strong>{{ result.paragraph_count }}</strong>
                    </div>
                    <div class="card">
                        <span class="label">Average Sentence Length</span>
                        <strong>{{ result.average_sentence_length }} words</strong>
                    </div>
                </div>

                <h3>Overall Feedback</h3>
                <p>{{ result.summary }}</p>

                <h3>Detailed Feedback</h3>
                <ul>
                    {% for item in result.feedback %}
                        <li>{{ item }}</li>
                    {% endfor %}
                </ul>
            </section>
        {% endif %}
    </main>
</body>
</html>
"""


def split_sentences(text):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [sentence for sentence in sentences if sentence.strip()]


def split_paragraphs(text):
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return [paragraph for paragraph in paragraphs if paragraph.strip()]


def get_essay_metrics(text):
    words = re.findall(r"\b[\w'-]+\b", text)
    sentences = split_sentences(text)
    paragraphs = split_paragraphs(text)
    average_sentence_length = round(len(words) / len(sentences), 1) if sentences else 0

    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "average_sentence_length": average_sentence_length,
    }


def extract_json_from_text(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def gemini_api_request(path, payload=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/{path}?key={GEMINI_API_KEY}"
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API error: {exc.code} {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not reach the Gemini API from this app.") from exc


def list_gemini_models():
    response = gemini_api_request("models")
    return response.get("models", [])


def pick_gemini_model():
    if MODEL_CACHE["name"]:
        return MODEL_CACHE["name"]

    preferred_models = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

    try:
        models = list_gemini_models()
    except RuntimeError:
        MODEL_CACHE["name"] = GEMINI_MODEL
        return GEMINI_MODEL

    supported = []
    for model in models:
        methods = model.get("supportedGenerationMethods", [])
        name = model.get("name", "")
        if "generateContent" in methods and name.startswith("models/"):
            supported.append(name.split("/", 1)[1])

    for candidate in preferred_models:
        if candidate in supported:
            MODEL_CACHE["name"] = candidate
            return candidate

    for candidate in supported:
        if "flash" in candidate:
            MODEL_CACHE["name"] = candidate
            return candidate

    for candidate in supported:
        if "gemini" in candidate:
            MODEL_CACHE["name"] = candidate
            return candidate

    raise RuntimeError("No Gemini model with generateContent support was found for this API key.")


def check_essay_with_gemini(text):
    prompt = f"""
You are an essay evaluator for students. You are strict, dont give high scores for bullshit. If the essay is too short like 3 sentences maximum dont be generous.x
Read the essay and respond with JSON only using this exact schema:
{{
  "score": 0,
  "summary": "one short paragraph",
  "feedback": [
    "feedback point 1",
    "feedback point 2",
    "feedback point 3",
    "feedback point 4"
  ]
}}

Rules:
- Score must be an integer from 0 to 100.
- Feedback should be specific, helpful, and easy for a student to understand.
- Mention strengths and weaknesses.
- Do not include markdown fences or any text outside the JSON.

Essay:
\"\"\"
{text}
\"\"\"
""".strip()

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }
    model_name = pick_gemini_model()

    try:
        raw_response = gemini_api_request(f"models/{model_name}:generateContent", payload)
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise

        MODEL_CACHE["name"] = None
        model_name = pick_gemini_model()
        raw_response = gemini_api_request(f"models/{model_name}:generateContent", payload)

    candidates = raw_response.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])
    response_text = "".join(part.get("text", "") for part in parts).strip()
    if not response_text:
        raise RuntimeError("Gemini returned an empty response.")

    parsed = extract_json_from_text(response_text)
    score = int(parsed.get("score", 0))
    feedback = parsed.get("feedback", [])

    if not isinstance(feedback, list) or not feedback:
        raise RuntimeError("Gemini response did not include valid feedback.")

    return {
        "score": max(0, min(score, 100)),
        "summary": str(parsed.get("summary", "")).strip() or "No summary was returned.",
        "feedback": [str(item).strip() for item in feedback if str(item).strip()],
    }


def analyze_essay(text):
    metrics = get_essay_metrics(text)
    gemini_result = check_essay_with_gemini(text)
    return {**metrics, **gemini_result}


@app.route("/", methods=["GET", "POST"])
def index():
    essay = ""
    result = None
    error = None

    if request.method == "POST":
        essay = request.form.get("essay", "").strip()

        if not essay:
            error = "Please enter an essay before submitting."
        else:
            try:
                result = analyze_essay(essay)
            except Exception as exc:
                error = str(exc)

    return render_template_string(PAGE_TEMPLATE, essay=essay, result=result, error=error)


if __name__ == "__main__":
    app.run(debug=True)
