# Extensão Chrome — Meetportation

Esta pasta é o modo Google Meet sem OBS. A extensão não gera vídeo sozinha. O programa Python precisa estar rodando e enviando frames para `ws://127.0.0.1:8765`.

O microfone não é trocado. Só a câmera de vídeo.

## Instalar e usar

1. Instale o programa na raiz do repositório com `setup.bat` (Windows) ou `./setup.sh` (macOS e Linux). O guia completo está no [README principal](../README.md).
2. No Chrome, abra `chrome://extensions`.
3. Ative **Modo do desenvolvedor**.
4. Clique em **Carregar sem compactação** e selecione esta pasta (`chrome-extension`), não a raiz do repositório.
5. Execute `run-meet.bat` ou `./run-meet.sh`. Espere a captura do fundo terminar.
6. Abra o Google Meet. Se a aba já estava aberta, recarregue.
7. Na seleção de câmera, use **Meetportation (teletransporte)**. Na maior parte dos casos ela já entra selecionada.

A extensão também pode ser usada no Teams e no Zoom abertos no navegador, no mesmo fluxo.

## O que cada arquivo faz

| Arquivo | Função |
|---|---|
| `manifest.json` | Declara a extensão e em quais páginas ela entra. |
| `background.js` | Único ponto que conecta ao Python. Recebe JPEG por WebSocket e repassa às abas. |
| `bridge.js` | Desenha cada frame num canvas escondido da página. |
| `inject.js` | Faz o site enxergar esse canvas como webcam, via `getUserMedia` e `enumerateDevices`. |

A conexão fica no service worker, e não no script da página, porque o Chrome bloqueia um site público de acessar `127.0.0.1` diretamente (Local Network Access).

## Porta

O padrão é `8765`, o mesmo de `run-meet`. Se você subir o Python com `--ws-port`, coloque a mesma porta em `WS_URL`, no topo de `background.js`, e recarregue a extensão em `chrome://extensions`.

## Se não aparecer imagem

| O que você vê | O que fazer |
|---|---|
| Texto verde "aguardando o Python" | A extensão está carregada e o WebSocket não conectou. Abra `run-meet` e confira se o terminal mostra `WebSocket ws://127.0.0.1:8765`. |
| Texto "conectando à extensão..." | Recarregue a extensão e depois a aba. |
| O Meet ainda usa a webcam real | Recarregue a aba depois de carregar a extensão. Selecione **Meetportation (teletransporte)** na lista de câmeras. |
| Mudou a porta e continua sem imagem | `background.js` e `--ws-port` precisam ser iguais. Recarregue a extensão depois de editar o arquivo. |

A janela de preview do Python permanece aberta enquanto você estiver na reunião. Fechar essa janela encerra o vídeo.
