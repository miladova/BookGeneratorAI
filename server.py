#!/usr/bin/env python3
"""
BookGenerator AI Web Server & REST API Bridge
Provides a sleek web interface and API endpoints for running the multi-agent book pipeline.
"""

import os
import sys
import json
import glob
import hashlib
import argparse
import threading
import time
import subprocess
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pipeline import book_dir_for, slugify
from generator.llm_client import SUPPORTED_PROVIDERS

PORT = int(os.getenv("BOOKGEN_PORT", "8080"))
HOST = os.getenv("BOOKGEN_HOST", "127.0.0.1")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
BOOKS_DIR = os.path.join(BASE_DIR, "books")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

## Global Jobs Storage
JOBS = {}
JOB_COUNTER = 0
JOB_LOCK = threading.Lock()
LAST_SCAN = 0.0
SCAN_INTERVAL = 5.0


def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default if default is not None else {}


def _job_snapshot():
    with JOB_LOCK:
        return sorted(JOBS.values(), key=lambda j: j.get("created_at", 0), reverse=True)


def _saved_job_id(book_dir):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in os.path.basename(book_dir))[-40:]
    digest = hashlib.sha1(os.path.abspath(book_dir).encode("utf-8")).hexdigest()[:8]
    return f"saved_{safe}_{digest}"


def _book_record(book_dir):
    """Builds a dashboard record from one book folder, or None if it is not a book."""
    manifest = _read_json(os.path.join(book_dir, "book.json"))
    docx_files = sorted(glob.glob(os.path.join(book_dir, "*.docx")))
    epub_files = sorted(glob.glob(os.path.join(book_dir, "*.epub")))
    manuscript_dir = os.path.join(book_dir, "manuscript")
    chapters = sorted(os.path.basename(p) for p in glob.glob(os.path.join(manuscript_dir, "chapter_*.md")))
    has_state = os.path.exists(os.path.join(book_dir, "state.db"))
    if not (docx_files or epub_files or has_state or chapters):
        return None

    title = (manifest.get("title") or os.path.basename(book_dir).replace("_", " ")).strip()
    completed = bool(docx_files or epub_files)
    mtime = max((os.path.getmtime(p) for p in docx_files + epub_files + [book_dir]), default=0)
    return {
        "job_id": _saved_job_id(book_dir),
        "title": title,
        "author": manifest.get("author") or "Unknown",
        "genre": manifest.get("genre") or "auto",
        "language": manifest.get("language") or "english",
        "provider": "saved",
        "status": "completed" if completed else "incomplete",
        "phase": "completed" if completed else "draft",
        "progress_percent": 100 if completed else 0,
        "message": (
            "Previously generated book found on disk. Read publishing/release_report.md before publishing."
            if completed else
            f"Saved progress found on disk ({len(chapters)} chapter(s)). Rerun the same command to resume."
        ),
        "active_title": title,
        "docx_path": os.path.abspath(docx_files[0]) if docx_files else "",
        "epub_path": os.path.abspath(epub_files[0]) if epub_files else "",
        "manuscript_dir": os.path.abspath(manuscript_dir),
        "book_dir": os.path.abspath(book_dir),
        "error": "",
        "chapters": chapters,
        "created_at": mtime,
    }


def discover_books(books_root=BOOKS_DIR, legacy_output_dir=OUTPUT_DIR):
    """Finds books written by this engine, newest first, including legacy output/ runs."""
    records = []
    if books_root and os.path.isdir(books_root):
        for entry in os.listdir(books_root):
            book_dir = os.path.join(books_root, entry)
            if os.path.isdir(book_dir):
                record = _book_record(book_dir)
                if record:
                    records.append(record)

    if legacy_output_dir and os.path.isdir(legacy_output_dir):
        docx_files = sorted(glob.glob(os.path.join(legacy_output_dir, "*.docx")))
        md_files = sorted(glob.glob(os.path.join(legacy_output_dir, "chapter_*.md")))
        if docx_files or md_files:
            docx_path = max(docx_files, key=os.path.getmtime) if docx_files else ""
            title = (os.path.basename(docx_path).replace(".docx", "").replace("_", " ")
                     if docx_path else "Legacy output")
            records.append({
                "job_id": _saved_job_id(legacy_output_dir),
                "title": title,
                "author": "Unknown",
                "genre": "auto",
                "language": "english",
                "provider": "saved",
                "status": "completed" if docx_path else "incomplete",
                "phase": "completed" if docx_path else "draft",
                "progress_percent": 100 if docx_path else 0,
                "message": "Legacy book found in output/.",
                "active_title": title,
                "docx_path": os.path.abspath(docx_path) if docx_path else "",
                "epub_path": "",
                "manuscript_dir": os.path.abspath(legacy_output_dir),
                "book_dir": os.path.abspath(legacy_output_dir),
                "error": "",
                "chapters": [os.path.basename(p) for p in md_files],
                "created_at": max((os.path.getmtime(p) for p in docx_files + md_files), default=0),
            })

    records.sort(key=lambda r: r["created_at"], reverse=True)
    return records


class BookGeneratorHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed_url = urllib.parse.urlparse(path)
        clean_path = urllib.parse.unquote(parsed_url.path)
        
        if clean_path in ["/", "/index.html"]:
            return os.path.join(WEB_DIR, "index.html")
        elif clean_path in ["/styles.css", "/app.js"]:
            return os.path.join(WEB_DIR, clean_path.lstrip("/"))
            
        target_path = os.path.abspath(os.path.join(WEB_DIR, clean_path.lstrip("/")))
        if not target_path.startswith(os.path.abspath(WEB_DIR) + os.sep):
            return os.path.join(WEB_DIR, "index.html")
        return target_path

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        if path in ["/api/status", "/api/jobs"]:
            jobs_list = _job_snapshot()
            running_jobs = [j for j in jobs_list if j.get("status") == "running"]
            if not running_jobs:
                maybe_scan_existing_books()
                jobs_list = _job_snapshot()
                running_jobs = [j for j in jobs_list if j.get("status") == "running"]
            latest_job = running_jobs[0] if running_jobs else (jobs_list[0] if jobs_list else {
                "status": "idle", "phase": "world", "progress_percent": 0,
                "message": "Ready to generate books.", "active_title": "", "docx_path": "", "chapters": []
            })
            response_data = {
                "active_job": latest_job,
                "running_count": len(running_jobs),
                "total_jobs": len(jobs_list),
                "jobs": jobs_list
            }
            response_data.update(latest_job)
            self.send_json_response(response_data)
            return

        elif path.startswith("/api/chapters/"):
            chap_num_str = path.replace("/api/chapters/", "").strip()
            try:
                chap_num = int(chap_num_str)
                filename = f"chapter_{chap_num:02d}.md"
                jobs = _job_snapshot()
                job = JOBS.get(query_params.get("job_id", [""])[0]) or (jobs[0] if jobs else {})
                filepath = os.path.join(job.get("manuscript_dir", OUTPUT_DIR), filename)
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.send_json_response({"chapter_number": chap_num, "content": content})
                else:
                    self.send_json_response({"error": "Chapter file not found yet."}, status=404)
            except ValueError:
                self.send_json_response({"error": "Invalid chapter number."}, status=400)
            return

        elif path == "/api/download":
            file_format = query_params.get("format", ["docx"])[0].lower()
            if file_format not in ("docx", "epub"):
                self.send_json_response({"error": "format must be docx or epub"}, status=400)
                return
            job_id = query_params.get("job_id", [None])[0]
            jobs = _job_snapshot()
            target_job = JOBS.get(job_id) if job_id else (jobs[0] if jobs else None)

            artifact = (target_job or {}).get(f"{file_format}_path") or ""
            if not os.path.exists(artifact):
                candidates = []
                if target_job and target_job.get("book_dir"):
                    candidates = glob.glob(os.path.join(target_job["book_dir"], f"*.{file_format}"))
                elif not job_id:
                    candidates = [r.get(f"{file_format}_path", "") for r in discover_books()]
                artifact = next((p for p in candidates if p and os.path.exists(p)), "")

            if artifact:
                content_type = (
                    "application/epub+zip" if file_format == "epub"
                    else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                filename = os.path.basename(artifact)
                ascii_filename = filename.encode("ascii", "ignore").decode("ascii") or f"book.{file_format}"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{urllib.parse.quote(filename)}"
                )
                self.send_header("Content-Length", str(os.path.getsize(artifact)))
                self.end_headers()
                with open(artifact, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_json_response({"error": f"No compiled {file_format.upper()} manuscript available yet."}, status=404)
            return

        # Fallback to static file server
        super().do_GET()

    def do_POST(self):
        global JOB_COUNTER
        if self.path == "/api/generate":
            # Browsers cannot send this type cross-site without a CORS approval, which this server never grants
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.send_json_response({"error": "Content-Type must be application/json"}, status=415)
                return
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            
            try:
                data = json.loads(body)
            except Exception:
                self.send_json_response({"error": "Invalid JSON body"}, status=400)
                return

            provider = (data.get("provider") or "ollama").lower()
            if provider not in SUPPORTED_PROVIDERS:
                self.send_json_response(
                    {"error": f"Unsupported provider '{provider}'. Choose one of: {', '.join(SUPPORTED_PROVIDERS)}."},
                    status=400,
                )
                return
            data["provider"] = provider

            with JOB_LOCK:
                JOB_COUNTER += 1
                job_id = f"job_{JOB_COUNTER}"
                data["job_id"] = job_id

            # Launch concurrent generation thread
            t = threading.Thread(target=run_generation_task, args=(job_id, data), daemon=True)
            t.start()

            self.send_json_response({"status": "started", "job_id": job_id, "message": f"Book generation job '{job_id}' launched successfully."})
            return

        self.send_json_response({"error": "Endpoint not found"}, status=404)

    def send_json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_generation_task(job_id, params):
    global JOBS
    title = (params.get("title") or "Untitled Book").strip()
    concept = (params.get("concept") or title).strip()
    author = (params.get("author") or "Unknown").strip()
    language = params.get("language") or "english"
    genre = params.get("genre") or "auto"
    provider = params.get("provider") or "ollama"
    model = (params.get("model") or "").strip()
    api_key = (params.get("api_key") or "").strip()
    ollama_url = params.get("ollama_url") or "http://localhost:11434"

    # Set environment variables for API key
    env_vars = os.environ.copy()
    if api_key:
        if provider == "gemini":
            env_vars["GEMINI_API_KEY"] = api_key
        elif provider == "openai":
            env_vars["OPENAI_API_KEY"] = api_key
        elif provider == "anthropic":
            env_vars["ANTHROPIC_API_KEY"] = api_key
        env_vars["LLM_API_KEY"] = api_key


    book_dir = os.path.join(BASE_DIR, book_dir_for(title))
    output_docx_path = os.path.join(book_dir, f"{slugify(title)}.docx")

    job_record = {
        "job_id": job_id,
        "title": title,
        "author": author,
        "genre": genre,
        "language": language,
        "provider": provider,
        "status": "running",
        "phase": "world",
        "progress_percent": 10,
        "message": f"World Builder Agent: Generating World Bible for '{title}'...",
        "active_title": title,
        "docx_path": output_docx_path,
        "epub_path": os.path.splitext(output_docx_path)[0] + ".epub",
        "manuscript_dir": os.path.join(book_dir, "manuscript"),
        "book_dir": book_dir,
        "error": "",
        "chapters": [],
        "created_at": time.time(),
    }
    with JOB_LOCK:
        # A live job supersedes the saved record for the same book folder.
        for existing_id, existing in list(JOBS.items()):
            if existing_id != job_id and existing.get("book_dir") == book_dir:
                JOBS.pop(existing_id, None)
        JOBS[job_id] = job_record

    chapters = str(params.get("chapters", "12"))
    cmd = [
        sys.executable, "-u", "main.py",
        "--title", title,
        "--concept", concept,
        "--author", author,
        "--language", language,
        "--genre", genre,
        "--provider", provider,
        "--chapters", chapters,
        "--output", output_docx_path
    ]
    if model:
        cmd.extend(["--model", model])
    if ollama_url:
        cmd.extend(["--ollama-url", ollama_url])

    print(f"\n[Web Server] Launching Book Generator process for '{title}' (Job: {job_id}): {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            env=env_vars,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        recent_lines = []
        for line in iter(proc.stdout.readline, ""):
            line_str = line.strip()
            print(f"  [AI Engine - {job_id}] {line_str}")
            if line_str:
                recent_lines = (recent_lines + [line_str])[-8:]

            if "Agent: World Builder" in line_str:
                job_record["phase"] = "world"
                job_record["progress_percent"] = 15
                job_record["message"] = "World Builder Agent: Creating setting and cultural rules..."
            elif "Agent: Character Architect" in line_str:
                job_record["phase"] = "char"
                job_record["progress_percent"] = 25
                job_record["message"] = "Character Architect Agent: Building voice fingerprints & profiles..."
            elif "Agent: Master Outliner" in line_str:
                job_record["phase"] = "outline"
                job_record["progress_percent"] = 35
                job_record["message"] = "Master Outliner Agent: Planning chapters and scenes..."
            elif line_str.startswith("CHAPTER "):
                job_record["phase"] = "draft"
                try:
                    num, total = line_str.split("CHAPTER ")[1].split(":")[0].split("/")
                    num, total = int(num), int(total)
                    job_record["progress_percent"] = 35 + int((num / total) * 55)
                    job_record["message"] = f"Prose Drafter & Adversarial Critics: Drafting Chapter {num}/{total}..."
                    
                    chap_file = f"chapter_{num:02d}.md"
                    if chap_file not in job_record["chapters"]:
                        job_record["chapters"].append(chap_file)
                except Exception:
                    pass
            elif "PHASE 4" in line_str or "PHASE 5" in line_str:
                job_record["phase"] = "docx"
                job_record["progress_percent"] = 95
                job_record["message"] = "Release review, publishing kit and DOCX/EPUB compilation..."

        proc.wait()

        if proc.returncode == 0 and os.path.exists(job_record["docx_path"]):
            job_record.update({
                "status": "completed",
                "phase": "completed",
                "progress_percent": 100,
                "message": f"Generated '{title}'. Read publishing/release_report.md before publishing."
            })
        elif proc.returncode == 0:
            job_record.update({
                "status": "failed",
                "message": "Engine exited without compiling a DOCX manuscript.",
                "error": recent_lines[-1] if recent_lines else "No DOCX output was produced."
            })
        else:
            job_record.update({
                "status": "failed",
                "message": "Engine run returned non-zero exit code.",
                "error": recent_lines[-1] if recent_lines else "Pipeline execution stopped unexpectedly."
            })

    except Exception as ex:
        print(f"[Web Server Error - {job_id}] {ex}")
        job_record.update({
            "status": "failed",
            "message": f"Execution error: {ex}",
            "error": str(ex)
        })



def scan_existing_books():
    """Adds books already on disk, without duplicating a live or recently finished job."""
    with JOB_LOCK:
        tracked_dirs = {
            os.path.abspath(job["book_dir"]): job
            for job in JOBS.values() if job.get("book_dir")
        }
        added = 0
        for record in discover_books():
            book_dir = record["book_dir"]
            existing = tracked_dirs.get(book_dir)
            if existing:
                # Keep the live record, but let a finished job pick up files it did not know about.
                if existing.get("status") != "running":
                    for key in ("docx_path", "epub_path", "chapters"):
                        if record.get(key):
                            existing[key] = record[key]
                continue
            JOBS[record["job_id"]] = record
            tracked_dirs[book_dir] = record
            added += 1
    if added:
        print(f"  ✓ [Disk Scanner] Added {added} book(s) found in books/ and output/.")


def maybe_scan_existing_books():
    """Throttles disk scans so idle polling stays cheap."""
    global LAST_SCAN
    now = time.time()
    if now - LAST_SCAN >= SCAN_INTERVAL:
        LAST_SCAN = now
        scan_existing_books()


def main():
    parser = argparse.ArgumentParser(description="BookGenerator AI web dashboard and REST API.")
    parser.add_argument("--host", default=HOST, help="Bind address (default: 127.0.0.1; use 0.0.0.0 to share)")
    parser.add_argument("--port", type=int, default=PORT, help="Port (default: 8080)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(BOOKS_DIR, exist_ok=True)
    os.makedirs(WEB_DIR, exist_ok=True)
    scan_existing_books()

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("  ⚠️  The dashboard has no authentication and can start paid LLM jobs.")
        print("     Only bind to a non-loopback address on a trusted network.")

    server = ThreadingHTTPServer((args.host, args.port), BookGeneratorHandler)
    display_host = "localhost" if args.host in ("0.0.0.0", "::") else args.host
    print("=" * 80)
    print("  BOOKGENERATOR AI - WEB APPLICATION SERVER")
    print("=" * 80)
    print(f"  ► Local Web UI: http://{display_host}:{args.port}")
    print(f"  ► Server root: {BASE_DIR}")
    print(f"  ► Press Ctrl+C to stop the server.")
    print("=" * 80 + "\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down BookGenerator AI web server...")
        server.server_close()


if __name__ == "__main__":
    main()

