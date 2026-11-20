"""Teste opcional da extensão real com Playwright, páginas simuladas e vídeo sintético.

Instale playwright e o Chromium de teste. Execute python -m tests.extension_e2e.
CHROMIUM_EXECUTABLE permite usar um Chromium de teste já instalado.
"""
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

from meetportation.wsserver import WebSocketSink


def run():
    sink = WebSocketSink(port=0)
    try:
        sink.send(np.full((32, 32, 3), 140, np.uint8))
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as browser:
            ext = Path(tmp, "extension")
            shutil.copytree(Path(__file__).resolve().parents[1] / "chrome-extension", ext)
            worker = ext / "background.js"
            worker.write_text(worker.read_text().replace("127.0.0.1:8765", f"127.0.0.1:{sink.port}"))
            ctx = browser.chromium.launch_persistent_context(
                Path(tmp, "profile"), channel="chromium", headless=True,
                executable_path=os.getenv("CHROMIUM_EXECUTABLE"),
                args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}", "--disable-background-networking"],
            )
            ctx.set_default_timeout(6500)
            try:
                ctx.route("**://meet.google.com/**", lambda r: r.fulfill(content_type="text/html", body="<title>Fixture</title>"))
                ctx.route("http://localhost/**", lambda r: r.fulfill(content_type="text/html", body="<title>Local</title>"))
                first, second, local = [ctx.new_page() for _ in range(3)]
                first.goto("https://meet.google.com/first")
                second.goto("https://meet.google.com/second")
                local.goto("http://localhost/fixture")
                service = (ctx.service_workers or [ctx.wait_for_event("serviceworker")])[0]
                popup = ctx.new_page()
                popup.goto(service.url.replace("background.js", "popup.html"))
                canvas = "#meetportation-canvas"

                def action(page, button, expected, code=None):
                    page.bring_to_front()
                    popup.reload()
                    if code:
                        popup.locator("#code").evaluate("(el, value) => el.value = value", code)
                    popup.evaluate("document.querySelector('[role=status]').textContent = ''")
                    popup.locator(button).evaluate("el => el.click()")
                    popup.wait_for_function(
                        "msg => document.querySelector('[role=status]').textContent.includes(msg)", arg=expected
                    )

                for page in (first, second, local):
                    assert not page.locator(canvas).count()
                action(local, "form button:first-of-type", "Abra ou recarregue", sink.pairing_code)
                action(first, "form button:first-of-type", "Confira o código", "x" * 32)
                assert not first.locator(canvas).count()
                for page, other in ((first, second), (second, first)):
                    action(page, "form button:first-of-type", "Câmera ligada", sink.pairing_code)
                    page.wait_for_function("""() => {
                      const c = document.querySelector('#meetportation-canvas');
                      return c && c.getContext('2d').getImageData(0, 0, 1, 1).data[0] === 140;
                    }""")
                    assert page.evaluate("""async () => (await navigator.mediaDevices.enumerateDevices())
                        .some(d => d.deviceId === 'meetportation-cam')""")
                    other.locator(canvas).wait_for(state="detached")
                    assert not local.locator(canvas).count()
                action(second, "#stop", "desligado")
                second.locator(canvas).wait_for(state="detached")
                action(first, "form button:first-of-type", "Câmera ligada", sink.pairing_code)
                first.reload()
                assert not first.locator(canvas).count()
                popup.locator("#code").evaluate("(el, v) => el.value = v", sink.pairing_code)
                popup.locator("form button:first-of-type").evaluate("el => el.click()")
                popup.wait_for_function("document.querySelector('[role=status]').textContent.includes('aba mudou')")
                assert not first.locator(canvas).count()
                print("OK: pareamento, JPEG, isolamento entre abas, desligamento e recarga.")
            finally:
                ctx.close()
    finally:
        sink.close()


if __name__ == "__main__":
    run()
