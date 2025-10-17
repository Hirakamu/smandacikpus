from flask import Blueprint, render_template, request, abort, render_template_string, jsonify
from dbapi import ReadsAPI
from markdown import markdown
from functools import lru_cache
import datetime, json, csv, smtplib

bp = Blueprint("site", __name__)

@bp.route("/")
def home():
    q = request.args.get('q', '') or ''
    page = max(1, int(request.args.get('page',1)))
    limit = 10
    offset = (page - 1) * limit
    data = ReadsAPI.pageList(offset,limit,q)
    items = data.get("items", [])
    
    for a in items:
        if "uuid" in a:
            a["uuid"] = a["uuid"].replace("-", "")
    
    return render_template(
        "index.html",
        articles=items
    )


@bp.route("/baca/<uuid>")
@lru_cache(maxsize=1024)
def read(uuid: str):
    p = ReadsAPI.read(uuid)
    if not p:
        abort(404)

    p["content"] = markdown(p["content"], extensions=["fenced_code", "tables"])
    return render_template("baca.html", page=p)

@bp.route('/ujian')
def index():
    ua = request.headers.get("User-Agent","")
    allowed = "cbt-exam-browser"  # exact identifier students' browser sends
    if allowed in ua.lower():
        # serve normal exam page
        return "<h1>Exam page</h1>"
    # serve warning + JS that collects device info and posts to /report
    page = """
<!doctype html><meta charset="utf-8">
<title>Unauthorized Browser</title>
<script>
alert("Unauthorized browser detected. Device information will be collected and reported.");
// collect device info
const payload = {
  ts: new Date().toISOString(),
  userAgent: navigator.userAgent,
  platform: navigator.platform,
  language: navigator.language || navigator.languages,
  screen: {w: screen.width, h: screen.height, colorDepth: screen.colorDepth},
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  cookiesEnabled: navigator.cookieEnabled,
  hardwareConcurrency: navigator.hardwareConcurrency || null,
  deviceMemory: navigator.deviceMemory || null,
  doNotTrack: navigator.doNotTrack || null
};
// optional: canvas fingerprint (best-effort)
try {
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d");
  ctx.textBaseline = "top";
  ctx.font = "14px 'Arial'";
  ctx.fillText("cbt-fp-test-"+Math.random(), 2, 2);
  payload.canvasHash = c.toDataURL();
} catch(e){}
fetch("/report", {
  method: "POST",
  headers: {"Content-Type":"application/json"},
  body: JSON.stringify(payload),
  keepalive: true
}).catch(()=>{});
</script>
<h1>Unauthorized browser</h1>
<p>Your browser is not the approved CBT client. This incident will be reported.</p>
"""
    return render_template_string(page), 403





JSON_FILE = "reports.json"

@bp.route("/report", methods=["POST"])
def report():
    ip = request.remote_addr
    headers = dict(request.headers)
    try:
        client = request.get_json(force=True)
    except:
        client = {}
    ts = datetime.datetime.utcnow().isoformat()

    record = {
        "timestamp": ts,
        "ip": ip,
        "headers": headers,
        "client": client
    }

    # append each entry as a separate JSON object (JSONL format)
    with open(JSON_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return "", 200

