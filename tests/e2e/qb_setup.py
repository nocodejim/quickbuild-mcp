"""Drive the QuickBuild 16 first-run setup wizard headlessly (throwaway e2e stack only).

Standard library only, so it runs on any host with Python 3 (no install needed):

    python3 -I tests/e2e/qb_setup.py --url http://127.0.0.1:18810 --user admin --password ...

The wizard has four pages: administrator account, system setting (server URL, global storage
directory), email setting (an SMTP host is mandatory), and finish. Exits 0 when the wizard
completes (or was already completed), 1 otherwise.
"""
import argparse
import html
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="QuickBuild base URL as seen from this host")
    parser.add_argument("--user", required=True, help="administrator account to create")
    parser.add_argument("--password", required=True, help="administrator password")
    parser.add_argument(
        "--server-url",
        default="http://qb-server:8810",
        help="'URL to access QuickBuild' as agents see it (compose network name)",
    )
    parser.add_argument(
        "--storage-dir",
        default="/var/lib/quickbuild/storage",
        help="global storage directory (must be outside the install dir /opt/quickbuild)",
    )
    parser.add_argument("--smtp-host", default="localhost", help="SMTP host (required by the wizard)")
    return parser.parse_args()


class Wizard:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def fetch(self, url: str, data: dict | None = None) -> tuple[str, str]:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        with self.opener.open(url, body, timeout=120) as resp:
            return resp.geturl(), resp.read().decode("utf-8", "replace")


def text_of(page: str) -> str:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


def form_fields(page: str) -> tuple[str, str, dict, list]:
    """Return (form id, action, current field values, wizard button names) of a Wicket page."""
    form = re.search(r'<form id="([^"]+)" method="post" action="([^"]+)"', page)
    if not form:
        raise RuntimeError("no wizard form on page")
    fields: dict[str, str] = {}
    for tag in re.findall(r"<input[^>]*>", page):
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        kind = (re.search(r'type="([^"]+)"', tag) or [None, "text"])[1]
        if kind in ("button", "submit"):
            continue
        if kind in ("checkbox", "radio") and "checked" not in tag:
            continue
        value = re.search(r'value="([^"]*)"', tag)
        fields[name.group(1)] = html.unescape(value.group(1)) if value else ""
    for select in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', page, re.S):
        option = (
            re.search(r'<option[^>]*selected="selected"[^>]*value="([^"]*)"', select.group(2))
            or re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', select.group(2))
            or re.search(r'<option[^>]*value="([^"]*)"', select.group(2))
        )
        fields[select.group(1)] = option.group(1) if option else ""
    buttons = re.findall(r"e\.name=&#039;(\w+)&#039;", page)
    return form.group(1), html.unescape(form.group(2)), fields, buttons


def set_property(
    fields: dict, index: int, value: str, *, group: str = "", only_if_empty: bool = False
) -> None:
    """Set the index-th bean property input of the current wizard page.

    Text inputs end in ":editor:editor:wrapper:input"; password inputs in ":editor:editor:input".
    """
    marker = f":{index}:property:editor:editor:"
    for key in fields:
        if group not in key or marker not in key:
            continue
        if "input" not in key.split(marker, 1)[1]:
            continue
        if not only_if_empty or not fields[key]:
            fields[key] = value


def main() -> int:
    args = parse_args()
    wizard = Wizard(args.url)
    url, page = wizard.fetch(wizard.base + "/")
    for step in range(1, 8):
        if "/setup" not in url:
            print(f"Setup wizard complete (landed on {url})")
            return 0
        heading_match = re.search(r"(\d)\. ([A-Za-z ]+?)\s+\d of \d", text_of(page))
        heading = heading_match.group(0) if heading_match else "?"
        print(f"Wizard step {step}: {heading}")
        form_id, action, fields, buttons = form_fields(page)

        if step == 1 or "Administrator" in heading:
            basic = "editor:content:basicProperties"
            set_property(fields, 0, args.user, group=basic)
            set_property(fields, 1, args.password, group=basic)
            set_property(fields, 2, "QuickBuild Administrator", group=basic)
            set_property(fields, 3, "admin@example.com", group=basic)
        elif "System Setting" in heading:
            set_property(fields, 0, args.server_url)
            set_property(fields, 1, args.storage_dir)
        elif "Email Setting" in heading:
            set_property(fields, 0, args.smtp_host, only_if_empty=True)

        button = "finish" if "finish" in buttons else "next"
        fields[f"{form_id}_hf_0"] = ""
        fields[button] = "x"
        url, page = wizard.fetch(urllib.parse.urljoin(wizard.base + "/", action), fields)
        errors = re.findall(r'class="[^"]*feedbackPanelERROR[^"]*"[^>]*>([^<]+)', page)
        if errors:
            print("  wizard errors:", [e.strip() for e in errors][:5])

    print(f"Setup wizard did not finish; last page: {url}")
    print(text_of(page)[:1500])
    return 1


if __name__ == "__main__":
    sys.exit(main())
