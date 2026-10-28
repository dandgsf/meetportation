# Meetportation

Efeito de teletransporte para a câmera da reunião. Encoste dois dedos na testa e você some do Google Meet, do Teams ou do Zoom, com um efeito curto e um som. Repita o gesto e você volta.

Tudo roda na sua máquina: visão computacional com MediaPipe, efeito em OpenCV e saída como uma webcam que o aplicativo de reunião enxerga normalmente. Não há conta, servidor externo nem chave de API.

## Como funciona

```
Webcam → MediaPipe (mão, rosto, silhueta) → detector do gesto → efeito → câmera de saída → Meet / Teams / Zoom
```

1. **Fundo vazio.** Na primeira execução você sai do quadro por cerca de 4 segundos. O programa fotografa o cenário e é essa imagem que a reunião vê quando você some. Não precisa de tela verde.
2. **Gesto.** Indicador e médio esticados e juntos, anelar e mínimo dobrados, pontas dos dedos na testa. A regra é geométrica sobre os 21 pontos da mão, então funciona com a mão inclinada e a qualquer distância da câmera. O gesto precisa durar cerca de 170 ms e só rearma quando você tira a mão da testa.
3. **Efeito.** Em cerca de 0,3 s a silhueta pisca, ganha um rastro horizontal e um brilho ciano, e some sobre o fundo. O som toca em `assets/teleport.wav`.
4. **Saída.** Dois modos, descritos abaixo.

## Requisitos

- Python 3.10, 3.11, 3.12 ou 3.13, 64 bits. O MediaPipe ainda não publica pacote para Python 3.14.
- Uma webcam.
- Para o modo sem OBS: Google Chrome.
- Para o modo de câmera virtual no Windows e no macOS: [OBS Studio](https://obsproject.com/) 30 ou mais novo, só pelo driver. O OBS fica fechado durante o uso.
- No Linux, o modo de câmera virtual usa v4l2loopback.

Os modelos de visão (~8 MB) são baixados na primeira execução para a pasta `models/`, que não entra no Git. Depois disso o programa funciona offline.

## Instalação

### Windows

1. Instale o Python 3.12 em [python.org](https://www.python.org/downloads/) e marque **Add python.exe to PATH**.
2. Baixe este repositório e extraia numa pasta sem acentos, por exemplo `D:\meetportation`.
3. Dê dois cliques em `setup.bat`. O script cria o ambiente virtual e instala as dependências de `requirements.txt`.

### macOS e Linux

Na raiz do repositório:

```bash
chmod +x setup.sh run.sh run-meet.sh
./setup.sh
```

No macOS, o Terminal pede permissão de câmera na primeira execução. Conceda em Ajustes do Sistema.

## Modo Google Meet, sem OBS

Use este modo no Google Meet, no Teams web e no Zoom web.

1. No Chrome, abra `chrome://extensions`.
2. Ative **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação** e escolha a pasta `chrome-extension`.
4. Na raiz do repositório, execute `run-meet.bat` no Windows ou `./run-meet.sh` no macOS e no Linux.
5. Quando a contagem aparecer, saia do quadro até a captura do fundo terminar.
6. Abra o Meet. A câmera **Meetportation (teletransporte)** já vem selecionada. Se a aba já estava aberta, recarregue.

O Python envia o vídeo por WebSocket em `ws://127.0.0.1:8765`. A extensão troca a câmera só dentro da aba. O microfone continua o da máquina. O passo a passo da extensão, arquivo por arquivo, está em [chrome-extension/README.md](chrome-extension/README.md).

A porta padrão é `8765`. Se mudar com `--ws-port`, altere também `WS_URL` em `chrome-extension/background.js`.

## Modo câmera virtual

Use este modo no Teams e no Zoom instalados no computador, e em qualquer outro programa que escolha uma webcam.

1. Instale o OBS Studio 30 ou mais novo.
   - **macOS:** abra o OBS uma vez, clique em **Start Virtual Camera**, autorize a extensão em Ajustes do Sistema, clique em **Stop Virtual Camera** e feche o OBS.
   - **Windows:** o driver é instalado junto com o OBS.
   - **Linux:** o backend é o v4l2loopback.
2. Deixe o OBS fechado.
3. Execute `run.bat` no Windows ou `./run.sh` no macOS e no Linux.
4. Saia do quadro na contagem inicial.
5. No aplicativo de reunião, escolha a câmera **OBS Virtual Camera**.

## Durante a reunião

A janela de preview precisa continuar aberta. Pode minimizar. Ela é a câmera que a reunião recebe.

| Tecla | Ação |
|---|---|
| `espaço` | teletransporte manual |
| `b` | recapturar o fundo |
| `d` | ligar ou desligar o diagnóstico do gesto |
| `q` | sair |

- Dois dedos na testa: você some. Solte a mão e repita: você volta.
- Câmera fixa e luz estável. Se mexer a câmera ou a luz mudar, aperte `b`.
- Trave a exposição automática da webcam no software do fabricante. Sem isso, o brilho do cômodo muda quando você sai do quadro e o fundo capturado deixa de coincidir com o ao vivo.
- O som sai no alto-falante. Para os outros participantes ouvirem, use um cabo de áudio virtual (VB-CABLE no Windows, BlackHole no macOS).

## Opções

No macOS e no Linux, troque `run.bat` por `./run.sh`. O `run-meet` aceita as mesmas opções.

```bash
run.bat --source 1              # outra webcam
run.bat --away live             # fundo ao vivo com segmentação (mais realista, mais CPU)
run.bat --record reel.mp4       # grava o que a reunião vê
run.bat --radius 0.8 --hold 4   # gesto mais tolerante e mais rápido
run.bat --proc-width 480        # mais leve para máquinas modestas
run.bat --sound meu_som.wav     # outro efeito sonoro
run.bat --recapture             # força nova captura do fundo
run.bat --mute                  # sem som
run.bat --no-mirror             # preview sem espelhar
run.bat --headless              # sem janela de preview
```

Ordem do som, quando `--sound` não é informado:

1. `data/teleport.wav`, se você colocar um arquivo seu nessa pasta
2. `assets/teleport.wav`, o som que vem no repositório
3. um som sintetizado por `meetportation/audio.py`, gerado em `data/teleport.wav`

`data/` não é versionada. Um som pessoal fica só na sua máquina.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| O Meet não mostra imagem na câmera Meetportation | Confirme que `run-meet` está aberto. Em `chrome://extensions`, recarregue a extensão e atualize a aba do Meet. |
| Quadro escuro com o texto "aguardando o Python" | A extensão está ativa e não encontrou o programa. Abra `run-meet`. |
| `OBS Virtual Camera is not installed` | Instale o OBS 30 ou mais novo. No macOS, ative a câmera virtual uma vez, como descrito acima. |
| Teams ou Zoom não lista "OBS Virtual Camera" | Abra o Meetportation antes do aplicativo de reunião, ou reinicie o aplicativo. |
| O gesto não dispara | Aperte `d` e observe a distância entre os dedos e a testa. Tente `--radius 0.8`. |
| O efeito dispara sozinho | Diminua `--radius` ou aumente `--hold`. |
| Webcam preta ou câmera errada | Tente `--source 1` ou outro índice. |
| A imagem de fundo não combina com a sala | Aperte `b` e saia do quadro de novo. Trave a exposição da webcam. |

## Estrutura

```
meetportation/
├─ gesture.py     detector do gesto e debounce (geometria, testável sem câmera)
├─ detector.py    MediaPipe Tasks: mãos, rosto e segmentação
├─ fx.py          fundo vazio, máscara da pessoa e efeito visual
├─ engine.py      estados: presente → sumindo → fora → aparecendo
├─ audio.py       reprodução do som e gerador sintetizado
├─ output.py      câmera virtual (pyvirtualcam) e gravação MP4
├─ wsserver.py    saída por WebSocket para a extensão do Chrome
└─ app.py         linha de comando, captura do fundo, preview e atalhos
assets/
├─ teleport.wav         som padrão
└─ teleport-synth.wav   versão sintetizada por código
chrome-extension/       extensão que entrega o vídeo ao Meet
tests/
├─ test_core.py         testes de gesto, debounce, efeito, fundo e ciclo completo
└─ e2e.py               roda o app com vídeo sintético e gera um contact sheet
```

## Testes

Com o ambiente do `setup` ativado, na raiz do repositório:

```bash
python -m unittest tests.test_core -v
python -m tests.e2e saida_e2e
```

O teste de ponta a ponta grava em `saida_e2e/`. Essa pasta está no `.gitignore`.

Validado em Windows 11, macOS (Apple Silicon) e Linux.

## Aviso sobre terceiros

`assets/teleport.wav` foi gerado com o ElevenLabs Sound Effects. Não é áudio de anime. `assets/teleport-synth.wav` é sintetizado pelo código deste repositório. Dragon Ball e os personagens associados são marcas de seus titulares. Este repositório não inclui imagem nem áudio original da obra.

## Contato

Danilo Fernandes, [Marktracking](https://marktracking.com.br).

- Site: [marktracking.com.br](https://marktracking.com.br)
- Instagram: [@danilodgsf](https://www.instagram.com/danilodgsf/)
- E-mail: [contato@marktracking.com.br](mailto:contato@marktracking.com.br)
