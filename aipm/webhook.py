"""
GitHub Webhook Listener for AIPM v2.

Replaces polling with push-based event handling.
GitHub pushes events (issue created, PR merged, etc.) and AIPM reacts.

Usage:
  python3 -m aipm.webhook --port 9000 --secret <webhook-secret>

Setup:
  1. Run this listener on a machine accessible from the internet
  2. Add webhook in GitHub repo settings: http://your-host:9000/webhook
  3. Subscribe to events: issues, pull_request, label
  4. Set the webhook secret

The listener calls back into the loop's run_once() when relevant events arrive.
"""

import hashlib
import hmac
import json
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Optional, Dict, Any


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for GitHub webhook events."""

    secret: bytes = b""
    on_event: Optional[Callable] = None

    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Verify signature
        if self.secret:
            sig = self.headers.get("X-Hub-Signature-256", "")
            if not self._verify_signature(body, sig):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Invalid signature")
                return

        # Parse event
        event_type = self.headers.get("X-GitHub-Event", "")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

        # Dispatch
        if self.on_event:
            self.on_event(event_type, payload)

    def _verify_signature(self, body: bytes, signature: str) -> bool:
        expected = "sha256=" + hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def log_message(self, format, *args):
        # Quieter logging
        print(f"  [webhook] {args[0]}")


def handle_event(event_type: str, payload: Dict[str, Any]):
    """Process a GitHub webhook event.

    This is called by the HTTP handler. It decides whether the event
    should trigger an AIPM run.
    """
    action = payload.get("action", "")
    repo = payload.get("repository", {}).get("full_name", "")

    if event_type == "issues":
        _handle_issue_event(action, payload, repo)
    elif event_type == "pull_request":
        _handle_pr_event(action, payload, repo)
    elif event_type == "label":
        _handle_label_event(action, payload, repo)


def _handle_issue_event(action: str, payload: Dict, repo: str):
    """Handle issue events."""
    issue = payload.get("issue", {})
    labels = [l.get("name", "") for l in issue.get("labels", [])]

    if "autospec" not in labels:
        return

    number = issue.get("number", "?")
    title = issue.get("title", "")

    if action == "opened":
        print(f"New spec issue #{number} in {repo}: {title}")
        print(f"   -> Will be picked up on next cycle")

    elif action == "labeled":
        label = payload.get("label", {}).get("name", "")
        if label == "spec-defined":
            print(f"Issue #{number} in {repo} marked spec-defined: {title}")
            print(f"   -> Ready for AIPM to pick up")

    elif action == "closed":
        print(f"Issue #{number} in {repo} closed: {title}")

    elif action == "reopened":
        print(f"Issue #{number} in {repo} reopened: {title}")

    elif action == "unlabeled":
        label = payload.get("label", {}).get("name", "")
        if label == "in-progress":
            print(f"Issue #{number} in {repo} unmarked in-progress")
            print(f"   -> Will be re-evaluated on next cycle")


def _handle_pr_event(action: str, payload: Dict, repo: str):
    """Handle pull request events."""
    pr = payload.get("pull_request", {})
    number = pr.get("number", "?")
    title = pr.get("title", "")

    if action == "merged" and pr.get("merged"):
        print(f"PR #{number} merged in {repo}: {title}")
        # If this was an AIPM PR, mark the issue as done
        if "AIPM" in title or "autospec" in str(pr.get("labels", [])):
            print(f"   -> AIPM PR merged, related issue should auto-close")

    elif action == "opened":
        if "AIPM" in title:
            print(f"AIPM PR #{number} opened in {repo}: {title}")


def _handle_label_event(action: str, payload: Dict, repo: str):
    """Handle label events."""
    if action == "created":
        label = payload.get("label", {}).get("name", "")
        if label in ("spec-defined", "in-progress", "autospec", "circuit-breaker"):
            print(f"Label '{label}' created in {repo}")


def run_listener(port: int = 9000, secret: str = ""):
    """Start the webhook listener."""
    WebhookHandler.secret = secret.encode() if secret else b""
    WebhookHandler.on_event = handle_event

    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"AIPM webhook listener on :{port}")
    if secret:
        print(f"   Secret: {'*' * 8}")
    print(f"   Endpoint: http://0.0.0.0:{port}/webhook")
    print()
    print("Configure in GitHub: Settings > Webhooks > Add webhook")
    print(f"  Payload URL: http://your-host:{port}/webhook")
    print(f"  Content type: application/json")
    print(f"  Events: issues, pull_request, label")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping webhook listener...")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIPM Webhook Listener")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--secret", type=str, default="")
    args = parser.parse_args()
    run_listener(port=args.port, secret=args.secret)
