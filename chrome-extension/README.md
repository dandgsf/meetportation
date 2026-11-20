# Extensão Chrome — Meetportation

Esta pasta é o modo Google Meet sem OBS. A extensão não gera vídeo sozinha. O programa Python precisa estar rodando e enviando frames para `ws://127.0.0.1:8765`.

O microfone não é trocado. Só a câmera de vídeo.

## Instalar e usar

1. Instale o programa na raiz do repositório com `setup.bat` (Windows) ou `./setup.sh` (macOS e Linux). O guia completo está no [README principal](../README.md).
2. No Chrome, abra `chrome://extensions`.
3. Ative **Modo do desenvolvedor**.
4. Clique em **Carregar sem compactação** e selecione esta pasta (`chrome-extension`), não a raiz do repositório.
5. Execute `run-meet.bat` ou `./run-meet.sh`. Espere a captura do fundo terminar.
6. Abra a reunião no Google Meet. Clique no ícone da extensão nessa aba. Cole o código exibido no terminal e clique em **Ligar nesta aba**. A tecla **P** também mostra ou oculta o código no preview do Python.
7. Selecione **Meetportation (teletransporte)** no Meet. Use **Desligar nesta aba** para parar. Ao recarregar a página, autorize de novo. Se mudar de aba de reunião, pareie a nova aba para transferir o vídeo.

O código muda a cada execução do Python. O modo `--ws --headless` requer um terminal interativo. Para o Teams e o Zoom, use a câmera virtual conforme o guia principal.

## O que cada arquivo faz

| Arquivo | Função |
|---|---|
| `manifest.json` | Declara a extensão e em quais páginas ela entra. |
| `background.js` | Único ponto que conecta ao Python. Autentica a conexão local e encaminha JPEG ao documento selecionado. |
| `bridge.js` | Desenha cada frame num canvas escondido da página. |
| `inject.js` | Faz o site enxergar esse canvas como webcam, via `getUserMedia` e `enumerateDevices`. |

A conexão fica no service worker, e não no script da página, porque o Chrome bloqueia um site público de acessar `127.0.0.1` diretamente (Local Network Access).

## Porta

O padrão é `8765`, o mesmo de `run-meet`. Se você subir o Python com `--ws-port`, coloque a mesma porta em `WS_URL`, no topo de `background.js`, e recarregue a extensão em `chrome://extensions`.

## Se não aparecer imagem

| O que você vê | O que fazer |
|---|---|
| Código recusado | Abra `run-meet` e cole o código desta execução no popup. |
| O popup pede para recarregar a aba | Recarregue a aba do Google Meet e clique outra vez no ícone da extensão. |
| O Meet ainda usa a webcam real | Recarregue a aba depois de carregar a extensão. Selecione **Meetportation (teletransporte)** na lista de câmeras. |
| Mudou a porta e continua sem imagem | `background.js` e `--ws-port` precisam ser iguais. Recarregue a extensão depois de editar o arquivo. |

A janela de preview do Python permanece aberta enquanto você estiver na reunião. Fechar essa janela encerra o vídeo.
