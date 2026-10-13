# SoundTouch — Quartos e Sala por Wi-Fi

App Windows para a Bose SoundTouch SA-5 Quartos e Bose Cinemate Sala.
Captura a saída predefinida Windows através de WASAPI, codifica MP3 estéreo a
320 kbps e transmite por HTTP/UPnP à coluna. Não depende da cloud Bose.

## Utilização

A app arranca ao iniciar sessão no Windows e fica junto ao relógio.
Faça duplo clique no ícone verde para abrir o painel **SoundTouch**.
Escolha **Quartos**, **Sala** ou **Este PC** para decidir onde ouvir.
Ao mudar de coluna, a app para a anterior e adota o volume da nova coluna.
A última seleção é guardada para o próximo arranque. Também pode escolher
a saída **SoundTouch Wi-Fi** no seletor de som normal do Windows: a app deteta
essa seleção e estabelece a ligação automaticamente.

**Este PC** restaura a saída anterior e pausa a ponte. **Usar Spotify** liberta
a coluna para outra fonte. **Restabelecer ligação** volta a enviar áudio do PC.
A app não retoma à força se entretanto escolher Spotify.

O slider do painel e o volume Windows controlam o volume da coluna (0–100).
As teclas de volume e o botão de silenciar do Windows são sincronizados.
Mudanças na coluna também atualizam o slider Windows. Ao ligar, a app adota
o volume atual da coluna para evitar um salto para um valor antigo do PC.
O volume individual do VLC e de cada app continua a regular o sinal dessa app.

## Instalação e arranque

Requisitos: Windows 10/11 de 64 bits, Python 3.14 de 64 bits e as duas colunas
SoundTouch acessíveis na mesma rede. O painel atual tem as escolhas Quartos e
Sala; não é um controlador universal de todos os dispositivos DLNA.

1. Clone este repositório numa pasta permanente do PC.
2. Atualize os endereços IP em `config.example.json`, se necessário.
3. Abra PowerShell nessa pasta e execute `powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1`.
   O script cria `.venv`, instala as dependências e consulta as colunas para
   criar `config.json` com os seus identificadores reais. Não substitui uma
   configuração já existente.
4. Descarregue o pacote Windows VB-CABLE no [site oficial](https://vb-audio.com/Cable/)
   e extraia o conteúdo para `vendor\vbcable`. O driver de terceiros não é
   distribuído neste repositório. Se já estiver instalado, salte este passo.
5. Abra PowerShell como administrador e execute
   `powershell -NoProfile -ExecutionPolicy Bypass -File .\admin-setup.ps1`.
   O script cria a firewall e, se necessário, abre o instalador oficial para
   escolher **Install Driver**. Reinicie quando o instalador pedir.
6. Execute `.\.venv\Scripts\pythonw.exe .\bridge.py --panel` e depois
   `powershell -NoProfile -ExecutionPolicy Bypass -File .\install-shortcuts.ps1`.
   Fica criado o atalho **SoundTouch** no Ambiente de Trabalho e no arranque.

Se o VB-CABLE já era a saída predefinida ao configurar, selecione primeiro a
saída local no Windows e depois Quartos ou Sala no painel; assim a app guarda
a saída local que deve restaurar quando escolher **Este PC**.

`config.json`, logs, instaladores, cópias de drivers e resultados dos testes
são locais e ignorados pelo Git. Guarde à parte uma cópia de `config.json`
se quiser restaurar exatamente os endereços e a última seleção deste PC.

Ambiente Python privado em `.venv`. Atalhos no Ambiente de Trabalho e na pasta
Startup. `admin-setup.ps1` cria uma regra TCP 18788 apenas para os endereços das
duas colunas e abre o instalador oficial, assinado, de VB-CABLE quando necessário.
`add-sala-firewall.ps1` atualiza a regra existente para admitir as duas colunas.
A saída é renomeada através da política de áudio do Windows, sem alterar permissões do registo.
A instalação de VB-CABLE deve ser concluída na sua janela; o fabricante pede
reinício do PC. Não reinicie durante uma sessão com trabalho por guardar.

O nome `SoundTouch Wi-Fi` é aplicado à saída virtual local. A coluna física
continua a ser encontrada pela app, não é um dispositivo WASAPI nativo.
A saída virtual é necessária para encaminhar o áudio Windows para esta app.

## Limitações

Há atraso do codificador e do buffer da SoundTouch: pode ser inadequado para
jogos/chamadas e requer compensação no VLC ao ver vídeo. Não foi implementada
sincronização automática de vídeo. O atraso deve ser medido no equipamento.
A rede e a coluna têm de estar disponíveis. Grupos cujo mestre seja outra
coluna são indicados no registo e devem ser desagrupados na app SoundTouch.

A app verifica alterações da saída Windows e volta a capturá-la. O endereço
IP inicial é 192.168.1.88; SSDP tenta reencontrar o mesmo dispositivo se mudar.
A regra de firewall admite 192.168.1.88 e 192.168.1.90: atualize a regra
se mudar o IP da coluna, ou reserve ambos no DHCP do router.

Diagnóstico: `http://127.0.0.1:18788/status` e `bridge.log` (registo rotativo).
A transmissão só aceita pedidos da coluna e do localhost e usa URL aleatório.
Não captura microfone nem grava o áudio em disco.

## Verificação e diagnóstico

- `python -m py_compile bridge.py`: valida a sintaxe sem reproduzir áudio.
- `.\.venv\Scripts\python.exe .\check-speaker-switch.py`: testa reprodução
  e sincronização de volume em Sala e Quartos; altera temporariamente a fonte
  nas duas colunas. Feche primeiro a app para libertar a porta HTTP.
- `.\.venv\Scripts\python.exe .\generate-test-tone.py` e depois
  `.\.venv\Scripts\python.exe .\check-audio.py`: geram e reproduzem um tom
  suave, verificando captura de áudio real e envio à coluna pela app ativa.
- `inspect-outputs.py` e `test-realtek.py`: inspecionam saídas e testam
  diretamente a Realtek, respetivamente. O teste pode reproduzir tons audíveis.
- `restart-realtek.ps1`: ferramenta de reparação específica para o ASUS PB60;
  requer administrador, exporta o driver e reinicia apenas o dispositivo
  Realtek correspondente. Não faz parte do funcionamento normal da app.
- `realtek-effects.py`: diagnóstico opcional dos efeitos Realtek;
  `--disable` e `--restore` modificam/restauram a configuração, usando uma
  cópia local. Não foi necessário desativar efeitos na instalação original.

## Remover

Escolha Este PC, depois Sair no ícone junto ao relógio. Apague os atalhos de Startup e
do Ambiente de Trabalho. Remova a regra `SoundTouch Quartos - audio local`
num PowerShell administrador. Para remover VB-CABLE use o instalador oficial
e reinicie, conforme instruções do fabricante. A pasta da app pode ser
apagada depois de a fechar.

Fontes: https://vb-audio.com/Cable/ e
https://github.com/s0d3s/PyAudioWPatch.
