const code = document.querySelector("#code");
const target = chrome.tabs.query({ active: true, currentWindow: true }).then(async ([tab]) => {
  const { documentId } = await chrome.runtime.sendMessage({ type: "target", tabId: tab.id });
  return { tabId: tab.id, documentId };
}).catch(() => ({}));

async function send(type) {
  const status = document.querySelector('[role="status"]');
  try {
    const response = await chrome.runtime.sendMessage({ type, ...await target, code: code.value.trim() });
    status.textContent = response.message;
    if (response.ok) code.value = "";
  } catch {
    status.textContent = "Recarregue a extensão e a aba do Meet.";
  }
}
document.querySelector("form").onsubmit = (event) => { event.preventDefault(); send("pair"); };
document.querySelector("#stop").onclick = () => send("stop");
