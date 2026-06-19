#== Palavras do Samuel vulgo Macamandi ==
# Sair da tela cheia com o Esc foi ajustado
# Reduzir o frame rate milagrosamente tornou a minha caixinha de coontrole mais responsiva
# Agora ele roda a 5 fps, valeu professor Weslley TorresXD 

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageSequence, ImageDraw
import json
import os
import serial
import serial.tools.list_ports
import threading
import time

# CONFIGURAÇÕES GERAIS E ESTADO

S = 2.0 # Escala inicial das imagens, é bpm estar preparado para as telas miúdas
CONFIG_FILE = 'config_can.json'

def carregar_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
        except: pass
    return {
        "start_byte": "0x20", "end_byte": "0x1f", "id_drive": "0x50", "id_re": "0x60", 
        "id_bcm": "0x200", "id_vel": "0x100", "id_volante": "0x101", 
        "id_sens_frente": "0x400", "id_sens_tras": "0x401"
    }

def salvar_config(config_data):
    with open(CONFIG_FILE, 'w') as f: json.dump(config_data, f, indent=4)

config_atual = carregar_config()

carro = {
    "marcha": "P", "velocidade": 0, "volante": 0, 
    "dist_frente": 200, "dist_tras": 200, "portas_raw": 0x00
}


# GERENCIADOR DE IMAGENS

def carregar_imagem_segura(caminho):
    try:
        img_original = Image.open(caminho)
        if getattr(img_original, "is_animated", False):
            # É animado! Extrai os frames PRIMEIRO, depois converte pra RGBA
            frames = [f.copy().convert("RGBA") for f in ImageSequence.Iterator(img_original)]
            return frames, True
        else:
            # É estático! Converte normalmente
            return img_original.convert("RGBA"), False
    except FileNotFoundError:
        try: return Image.open('imagens/placeholder.png').convert("RGBA"), False
        except:
            img_erro = Image.new('RGBA', (64, 64), color='#ac3232')
            d = ImageDraw.Draw(img_erro)
            d.line((0,0,64,64), fill="#fff", width=2); d.line((0,64,64,0), fill="#fff", width=2)
            return img_erro, False

assets_originais = {
    'm_d': carregar_imagem_segura('imagens/marcha_drive.gif'),
    'm_r': carregar_imagem_segura('imagens/marcha_re.gif'),
    'volante': carregar_imagem_segura('imagens/volante_neutro.png'),
    'f_livre': carregar_imagem_segura('imagens/frente_livre.gif'),
    'f_vulto': carregar_imagem_segura('imagens/frente_vulto.gif'),
    'f_elefante': carregar_imagem_segura('imagens/frente_elefante.gif'),
    'f_cabum': carregar_imagem_segura('imagens/cabum.gif'),
    't_livre': carregar_imagem_segura('imagens/tras_livre.gif'),
    't_vulto': carregar_imagem_segura('imagens/tras_vulto.gif'),
    't_hidrante': carregar_imagem_segura('imagens/tras_hidrante.gif'),
    't_cabum': carregar_imagem_segura('imagens/cabum.gif'),
    
    # Camadas das Portas (BCM)
    'chassi': carregar_imagem_segura('imagens/carro_chassi.png'),
    'p_mot': carregar_imagem_segura('imagens/porta_mot.png'),
    'p_pass': carregar_imagem_segura('imagens/porta_pass.png'),
    'p_tesq': carregar_imagem_segura('imagens/porta_tesq.png'),
    'p_tdir': carregar_imagem_segura('imagens/porta_tdir.png'),
    'p_malas': carregar_imagem_segura('imagens/porta_malas.png'),
    'p_tanque': carregar_imagem_segura('imagens/tanque.png')
}

cache_tk = {}
frame_idx = {'marcha': 0, 'frente': 0, 'tras': 0}

# INTERFACE GRÁFICA: TELA CHEIA E ABAS
root = tk.Tk()
root.title('ADAS Diagnostic Tool - Full Cyberdeck')
root.attributes('-fullscreen', True)
root.configure(bg='#222034')

root.bind('<Escape>', lambda e: [root.attributes('-fullscreen', False), root.geometry("480x320")])

container = tk.Frame(root)
container.pack(fill='both', expand=True)

aba_dash = tk.Frame(container, bg='#222034')
aba_config = tk.Frame(container, bg='#1a1926')
aba_usb = tk.Frame(container, bg='#1a1926')

aba_dash.place(relx=0, rely=0, relwidth=1, relheight=1)
aba_config.place(relx=0, rely=0, relwidth=1, relheight=1)
aba_usb.place(relx=0, rely=0, relwidth=1, relheight=1)

lista_abas = [aba_dash, aba_config, aba_usb]
aba_atual_idx = 0

def alternar_abas(event=None):
    global aba_atual_idx
    aba_atual_idx = (aba_atual_idx + 1) % len(lista_abas)
    lista_abas[aba_atual_idx].tkraise()

root.bind('<Tab>', alternar_abas)


# ESCALA DINÂMICA (Das Imagens)

def alterar_escala(delta):
    global S
    S = max(0.5, min(5.0, S + delta)) # Vai de 0.5x até 5x de zoom

root.bind('.', lambda e: alterar_escala(0.25))
root.bind(',', lambda e: alterar_escala(-0.25))

# ABA 1: DASHBOARD

top_bar = tk.Frame(aba_dash, bg='#1a1926', highlightbackground="#df7126", highlightthickness=1)
top_bar.place(relx=0, rely=0, relwidth=1, relheight=0.1)

lbl_status_usb = tk.Label(top_bar, text="USB: OFFLINE", bg='#1a1926', fg='#ac3232', font=('Courier', 10, 'bold'))
lbl_status_usb.place(relx=0.02, rely=0.5, anchor='w')

lbl_velocidade_top = tk.Label(top_bar, text="VELOCIDADE: 0 km/h", bg='#1a1926', fg='#99e550', font=('Courier', 10, 'bold'))
lbl_velocidade_top.place(relx=0.98, rely=0.5, anchor='e')

scale_vel = tk.Scale(top_bar, from_=0, to=120, orient='horizontal', bg='#1a1926', fg='#5fcde4', highlightthickness=0, showvalue=0, command=lambda v: injeção_simulada('velocidade', v))
scale_vel.place(relx=0.53, rely=0.5, relwidth=0.15, anchor='center')
tk.Label(top_bar, text="Acelerar:", bg='#1a1926', fg='#cbdbfc', font=('Arial', 8)).place(relx=0.45, rely=0.5, anchor='e')

matriz_frame = tk.Frame(aba_dash, bg='#222034')
matriz_frame.place(relx=0, rely=0.1, relwidth=1, relheight=0.65)

colunas = []
for i in range(5):
    f = tk.Frame(matriz_frame, bg='#222034', highlightbackground="#1a1926", highlightthickness=1)
    f.place(relx=i*0.2, rely=0, relwidth=0.2, relheight=1)
    colunas.append(f)

titulos = ["MARCHA", "PORTAS", "VOLANTE", "FRENTE", "TRÁS"]
lbls_titulos, lbls_imagens, lbls_valores = [], [], []

for i in range(5):
    lbl_t = tk.Label(colunas[i], text=titulos[i], bg='#222034', fg='#df7126', font=('Courier', 10, 'bold'))
    lbl_t.place(relx=0.5, rely=0.05, anchor='center')
    lbls_titulos.append(lbl_t)
    
    lbl_img = tk.Label(colunas[i], bg='#222034')
    lbl_img.place(relx=0.5, rely=0.4, anchor='center')
    lbls_imagens.append(lbl_img)
    
    lbl_v = tk.Label(colunas[i], text="-", bg='#222034', fg='#cbdbfc', font=('Arial', 9))
    lbl_v.place(relx=0.5, rely=0.7, anchor='center')
    lbls_valores.append(lbl_v)

# Controles HIL
btn_drive = tk.Button(colunas[0], text="D", bg="#99e550", fg="#000", font=('Arial', 8, 'bold'), command=lambda: injeção_simulada('marcha', 'D'))
btn_drive.place(relx=0.1, rely=0.8, relwidth=0.35, relheight=0.15)
btn_re = tk.Button(colunas[0], text="R", bg="#ac3232", fg="#fff", font=('Arial', 8, 'bold'), command=lambda: injeção_simulada('marcha', 'R'))
btn_re.place(relx=0.55, rely=0.8, relwidth=0.35, relheight=0.15)

def ciclar_portas():
    estado = carro['portas_raw']
    # Lógica sequencial: Fechado -> Mot -> Pass -> TrásEsq -> TrásDir -> Malas -> Tanque -> Tudo -> Fechado
    sequencia = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x3F]
    
    try:
        idx_atual = sequencia.index(estado)
        novo_estado = sequencia[(idx_atual + 1) % len(sequencia)]
    except ValueError:
        novo_estado = 0x00 
        
    injeção_simulada('portas', novo_estado)

btn_portas = tk.Button(colunas[1], text="ALTERAR", bg="#df7126", fg="#000", font=('Arial', 8, 'bold'), command=ciclar_portas)
btn_portas.place(relx=0.1, rely=0.8, relwidth=0.8, relheight=0.15)

scale_vol = tk.Scale(colunas[2], from_=-90, to=90, orient='horizontal', bg='#222034', fg='#5fcde4', highlightthickness=0, showvalue=0, command=lambda v: injeção_simulada('volante', v))
scale_vol.place(relx=0.1, rely=0.8, relwidth=0.8, relheight=0.15)

scale_frente = tk.Scale(colunas[3], from_=10, to=200, orient='horizontal', bg='#222034', fg='#99e550', highlightthickness=0, showvalue=0, command=lambda v: injeção_simulada('frente', v))
scale_frente.set(200)
scale_frente.place(relx=0.1, rely=0.8, relwidth=0.8)

scale_tras = tk.Scale(colunas[4], from_=10, to=200, orient='horizontal', bg='#222034', fg='#99e550', highlightthickness=0, showvalue=0, command=lambda v: injeção_simulada('tras', v))
scale_tras.set(200)
scale_tras.place(relx=0.1, rely=0.8, relwidth=0.8)

# Sniffer, farejador de portas seriais
painel_inferior = tk.Frame(aba_dash, bg='#000')
painel_inferior.place(relx=0, rely=0.75, relwidth=1, relheight=0.25)
lista_sniffer = tk.Listbox(painel_inferior, bg='#000', fg='#5fcde4', bd=0, font=('Courier', 8))
lista_sniffer.place(relx=0.02, rely=0.1, relwidth=0.96, relheight=0.8)

def log_sniffer(msg):
    lista_sniffer.insert(tk.END, msg)
    if lista_sniffer.size() > 8: lista_sniffer.delete(0)
    lista_sniffer.yview(tk.END)

def injeção_simulada(sistema, valor):
    start, end = config_atual["start_byte"], config_atual["end_byte"]
    id_can, payload_hex, descricao = "0x00", "0x00", ""

    if sistema == 'marcha': 
        carro['marcha'] = valor
        id_can = config_atual["id_drive"] if valor == 'D' else config_atual["id_re"]
        descricao = f"ENGATE: {valor}"
    elif sistema == 'portas': 
        valor_int = int(valor)
        carro['portas_raw'] = valor_int
        id_can, payload_hex = config_atual["id_bcm"], hex(valor_int)
        descricao = f"BCM PORTAS: {payload_hex}"
    elif sistema == 'velocidade': 
        valor_int = int(valor)
        carro['velocidade'] = valor_int
        id_can, payload_hex = config_atual["id_vel"], hex(valor_int)
        descricao = f"VELOCIDADE: {valor_int} km/h"
    elif sistema == 'volante': 
        valor_int = int(valor)
        carro['volante'] = valor_int
        id_can, payload_hex = config_atual["id_volante"], hex(valor_int + 90)
        descricao = f"VOLANTE: {valor_int}°"
    elif sistema == 'frente': 
        valor_int = int(valor)
        carro['dist_frente'] = valor_int
        id_can, payload_hex = config_atual["id_sens_frente"], hex(valor_int)
        descricao = f"SENS FRENTE: {valor_int} cm"
    elif sistema == 'tras': 
        valor_int = int(valor)
        carro['dist_tras'] = valor_int
        id_can, payload_hex = config_atual["id_sens_tras"], hex(valor_int)
        descricao = f"SENS TRÁS: {valor_int} cm"

    log_sniffer(f"[IN] {start} 0x07 {id_can} {payload_hex} 0x00 0x00 {end} -> {descricao}")

# ABA 2 e ABA 3: (Configuração e USB)

tk.Label(aba_config, text="PAINEL DE CONFIGURAÇÃO (TAB para alternar)", bg='#1a1926', fg='#df7126', font=('Arial', 10, 'bold')).place(relx=0.5, rely=0.1, anchor='center')
campos_cfg = {}
labels_ids = [
    ("start_byte", "Start:"), ("end_byte", "End:"), ("id_drive", "Drive:"), ("id_re", "Ré:"), 
    ("id_bcm", "Portas:"), ("id_vel", "Velocid:"), ("id_volante", "Volante:"), 
    ("id_sens_frente", "Frente:"), ("id_sens_tras", "Trás:")
]
for i, (chave, texto) in enumerate(labels_ids):
    col, row = i % 3, i // 3
    tk.Label(aba_config, text=texto, bg='#1a1926', fg='#cbdbfc').place(relx=0.1 + (col*0.3), rely=0.3 + (row*0.15))
    ent = tk.Entry(aba_config, width=8); ent.insert(0, config_atual.get(chave, "0x00"))
    ent.place(relx=0.22 + (col*0.3), rely=0.3 + (row*0.15))
    campos_cfg[chave] = ent

def salvar_matriz():
    for chave, ent in campos_cfg.items(): config_atual[chave] = ent.get().strip().lower()
    salvar_config(config_atual)
    btn_salvar.config(text="SALVO!", bg="#99e550")
    root.after(2000, lambda: btn_salvar.config(text="SALVAR CONFIG", bg="#df7126"))

btn_salvar = tk.Button(aba_config, text="SALVAR CONFIG", bg="#df7126", fg="#222034", font=('Arial', 10, 'bold'), command=salvar_matriz)
btn_salvar.place(relx=0.5, rely=0.8, anchor='center')

# USB
tk.Label(aba_usb, text="CONEXÃO SERIAL (TAB para alternar)", bg='#1a1926', fg='#df7126', font=('Arial', 10, 'bold')).place(relx=0.5, rely=0.1, anchor='center')
combo_portas = ttk.Combobox(aba_usb, width=30, state="readonly")
combo_portas.place(relx=0.5, rely=0.35, anchor='center')

def atualizar_portas():
    combo_portas['values'] = [p.device for p in serial.tools.list_ports.comports()]
    if combo_portas['values']: combo_portas.current(0)
    else: combo_portas.set("Nenhuma porta...")

tk.Button(aba_usb, text='⟳ ATUALIZAR', bg='#ffffff', command=atualizar_portas).place(relx=0.5, rely=0.55, anchor='center')

thread_rodando = False; ser = None
def escutar_serial():
    global thread_rodando, ser
    try:
        while thread_rodando:
            if ser.is_open and ser.in_waiting > 0:
                linha = ser.readline().decode('utf-8', errors='ignore').strip().split()
                if len(linha) == 7 and linha[0] == config_atual["start_byte"] and linha[-1] == config_atual["end_byte"]:
                    id_can, payload = linha[2], linha[3]
                    v = int(payload, 16)
                    if id_can == config_atual["id_drive"]: root.after(0, injeção_simulada, 'marcha', 'D')
                    elif id_can == config_atual["id_re"]: root.after(0, injeção_simulada, 'marcha', 'R')
                    elif id_can == config_atual["id_bcm"]: root.after(0, injeção_simulada, 'portas', v)
                    elif id_can == config_atual["id_vel"]: root.after(0, injeção_simulada, 'velocidade', v)
                    elif id_can == config_atual["id_volante"]: root.after(0, injeção_simulada, 'volante', v - 90)
                    elif id_can == config_atual["id_sens_frente"]: root.after(0, injeção_simulada, 'frente', v)
                    elif id_can == config_atual["id_sens_tras"]: root.after(0, injeção_simulada, 'tras', v)
            time.sleep(0.01)
    except: desconectar_serial()

def conectar_serial():
    global thread_rodando, ser
    p = combo_portas.get().strip()
    if p and p != "Nenhuma porta...":
        try:
            ser = serial.Serial(p, 115200, timeout=1); thread_rodando = True
            lbl_status_usb.config(text="USB: CONECTADO", fg="#99e550")
            btn_conectar.config(text="DESCONECTAR", bg="#ac3232", fg="#ffffff", command=desconectar_serial)
            threading.Thread(target=escutar_serial, daemon=True).start(); alternar_abas()
        except: lbl_status_usb.config(text="ERRO NA PORTA", fg="#ac3232")

def desconectar_serial():
    global thread_rodando, ser
    thread_rodando = False
    if ser and ser.is_open: ser.close()
    lbl_status_usb.config(text="USB: OFFLINE", fg="#ac3232")
    btn_conectar.config(text="CONECTAR", bg="#5fcde4", fg="#222034", command=conectar_serial)

btn_conectar = tk.Button(aba_usb, text='CONECTAR', bg='#5fcde4', fg='#222034', font=('Arial', 10, 'bold'), command=conectar_serial)
btn_conectar.place(relx=0.5, rely=0.75, anchor='center')
atualizar_portas()

# MOTOR DE RENDERIZAÇÃO ANIMADA E CAMADAS

def renderizar_portas_bitmask(size):
    # Pega o chassi base
    base = assets_originais['chassi'][0].copy()
    raw = carro['portas_raw']
    
    # Cola as camadas por cima usando Alpha Composite se o bit estiver ativo
    if raw & 0x01: base.alpha_composite(assets_originais['p_mot'][0])
    if raw & 0x02: base.alpha_composite(assets_originais['p_pass'][0])
    if raw & 0x04: base.alpha_composite(assets_originais['p_tesq'][0])
    if raw & 0x08: base.alpha_composite(assets_originais['p_tdir'][0])
    if raw & 0x10: base.alpha_composite(assets_originais['p_malas'][0])
    if raw & 0x20: base.alpha_composite(assets_originais['p_tanque'][0])
    
    cache_tk['portas_tk'] = ImageTk.PhotoImage(base.resize((size, size), Image.Resampling.NEAREST))
    lbls_imagens[1].config(image=cache_tk['portas_tk'])

def atualizar_interface():
    tamanho_img = int(64 * S)
    
    c_fre = 'f_livre' if carro['dist_frente'] > 150 else 'f_vulto' if carro['dist_frente'] > 80 else 'f_elefante' if carro['dist_frente'] > 30 else 'f_cabum'
    c_tra = 't_livre' if carro['dist_tras'] > 150 else 't_vulto' if carro['dist_tras'] > 80 else 't_hidrante' if carro['dist_tras'] > 30 else 't_cabum'
    c_mar = 'm_d' if carro['marcha'] == 'D' else 'm_r'

    vol_raw = assets_originais['volante'][0]
    cache_tk['volante'] = ImageTk.PhotoImage(vol_raw.resize((tamanho_img, tamanho_img), Image.Resampling.NEAREST).rotate(-carro['volante']))
    lbls_imagens[2].config(image=cache_tk['volante'])

    renderizar_frame(0, c_mar, 'marcha', tamanho_img)
    renderizar_portas_bitmask(tamanho_img)
    renderizar_frame(3, c_fre, 'frente', tamanho_img)
    renderizar_frame(4, c_tra, 'tras', tamanho_img)

    lbls_valores[0].config(text=f"ENGATE: {carro['marcha']}")
    lbls_valores[1].config(text=f"RAW: {hex(carro['portas_raw'])}")
    lbls_valores[2].config(text=f"{carro['volante']}°")
    lbls_valores[3].config(text=f"{carro['dist_frente']} cm", fg='#ac3232' if carro['dist_frente']<=30 else '#cbdbfc')
    lbls_valores[4].config(text=f"{carro['dist_tras']} cm", fg='#ac3232' if carro['dist_tras']<=30 else '#cbdbfc')
    lbl_velocidade_top.config(text=f"VELOCIDADE: {carro['velocidade']} km/h")

def renderizar_frame(col_idx, asset_key, anim_key, size):
    asset_data, is_gif = assets_originais[asset_key]
    if is_gif:
        idx = frame_idx[anim_key] % len(asset_data)
        cache_tk[f"{anim_key}_tk"] = ImageTk.PhotoImage(asset_data[idx].resize((size, size), Image.Resampling.NEAREST))
        frame_idx[anim_key] += 1
    else:
        cache_tk[f"{anim_key}_tk"] = ImageTk.PhotoImage(asset_data.resize((size, size), Image.Resampling.NEAREST))
    lbls_imagens[col_idx].config(image=cache_tk[f"{anim_key}_tk"])

def loop_animacao():
    atualizar_interface()
    root.after(200, loop_animacao)

aba_dash.tkraise()
loop_animacao()
root.mainloop()

#Fim do código, vc leu tuuuudo isso? Que emoção :*D
