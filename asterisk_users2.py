#!/usr/bin/env python3
"""
Gestor de usuarios Asterisk PJSIP - Versión Corregida
"""

import subprocess
import sys
import os
import re
import json

# ─── RUTAS ────────────────────────────────────────────────────────────────────
CONFIG_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "asterisk_config.json")
EXTENSIONS_CONF = "/etc/asterisk/extensions.conf"
CONTEXTO_DEFAULT = "from-internal"
# ──────────────────────────────────────────────────────────────────────────────


# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────

def cargar_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None


def guardar_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"  [OK] Configuración guardada en {CONFIG_FILE}")


def pedir_config():
    print("\n" + "="*45)
    print("   CONFIGURACIÓN INICIAL")
    print("="*45)
    host = input("  Host de MariaDB [localhost]: ").strip() or "localhost"
    user = input("  Usuario de MariaDB [root]:   ").strip() or "root"
    pwd  = input("  Contraseña de MariaDB:       ").strip()
    db   = input("  Nombre de la base de datos [asterisk]: ").strip() or "asterisk"

    cfg = {"host": host, "user": user, "password": pwd, "database": db}

    print("\n  Probando conexión...")
    test = run_query_cfg("SELECT 1;", cfg)
    if test is None:
        print("  [!] No se pudo conectar. Revisa los datos.")
        return None

    print("  [OK] Conexión exitosa.")
    guardar = input("  ¿Guardar esta configuración? (s/n): ").strip().lower()
    if guardar == "s":
        guardar_config(cfg)
    return cfg


def run_query_cfg(sql, cfg):
    cmd = [
        "mysql",
        f"-h{cfg['host']}",
        f"-u{cfg['user']}",
        f"-p{cfg['password']}",
        cfg["database"],
        "-e", sql
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\n  [ERROR] {result.stderr.strip()}")
        return None
    return result.stdout.strip()

CFG = {}

def run_query(sql):
    return run_query_cfg(sql, CFG)


# ─── GESTIÓN DE EXTENSIONS.CONF (CORREGIDO) ───────────────────────────────────

def leer_conf():
    if not os.path.exists(EXTENSIONS_CONF):
        return ""
    with open(EXTENSIONS_CONF, "r") as f:
        return f.read()

def guardar_conf(contenido):
    with open(EXTENSIONS_CONF, "w") as f:
        f.write(contenido)

def extension_existe(ext_num, contenido):
    # Busca la extensión al inicio de línea para evitar falsos positivos
    patron = rf"^\s*exten\s*=>\s*{re.escape(ext_num)}\s*,"
    return bool(re.search(patron, contenido, re.MULTILINE))

def añadir_extension_conf(ext_num, pjsip_id):
    contenido = leer_conf()
    
    if extension_existe(ext_num, contenido):
        print(f"  [!] La extensión {ext_num} ya existe en {EXTENSIONS_CONF}. No se añadirá de nuevo.")
        return

    lineas = contenido.splitlines()
    nuevas = [
        f"exten => {ext_num},1,Dial(PJSIP/{pjsip_id})",
        f"exten => {ext_num},2,Hangup()"
    ]

    seccion_buscada = f"[{CONTEXTO_DEFAULT}]"
    idx_seccion = -1

    # Localizar la sección
    for i, linea in enumerate(lineas):
        if linea.strip() == seccion_buscada:
            idx_seccion = i
            break

    if idx_seccion != -1:
        # Buscar el final de esa sección (donde empieza otra '[' o final del archivo)
        idx_insertar = len(lineas)
        for i in range(idx_seccion + 1, len(lineas)):
            if lineas[i].strip().startswith("["):
                idx_insertar = i
                break
        
        # Insertar las líneas antes del final de la sección
        for nl in reversed(nuevas):
            lineas.insert(idx_insertar, nl)
    else:
        # Si la sección no existe, la creamos al final
        if lineas and lineas[-1].strip() != "":
            lineas.append("")
        lineas.append(seccion_buscada)
        lineas.extend(nuevas)

    guardar_conf("\n".join(lineas) + "\n")
    print(f"  [OK] Extensión {ext_num} añadida a la sección {seccion_buscada}.")

def eliminar_extension_conf(ext_num):
    contenido = leer_conf()
    lineas = contenido.splitlines()
    
    patron = rf"^\s*exten\s*=>\s*{re.escape(ext_num)}\s*,"
    nuevas_lineas = [l for l in lineas if not re.match(patron, l)]

    if len(lineas) == len(nuevas_lineas):
        print(f"  [!] No se encontró la extensión {ext_num} en extensions.conf.")
        return

    guardar_conf("\n".join(nuevas_lineas) + "\n")
    print(f"  [OK] Extensión {ext_num} eliminada de extensions.conf.")


# ─── ACCIONES ─────────────────────────────────────────────────────────────────

def añadir_usuario():
    print("\n── AÑADIR USUARIO ──")
    ext_id = input("  ID Usuario (ej: tel3):     ").strip()
    if not ext_id: return

    # Escapar comillas simples para SQL básico
    ext_id = ext_id.replace("'", "''")

    existe = run_query(f"SELECT id FROM ps_auths WHERE id='{ext_id}';")
    if existe:
        print(f"  [!] El usuario '{ext_id}' ya existe en la DB.")
        return

    password  = input("  Contraseña:                ").strip().replace("'", "''")
    ext_num   = input("  Número extensión (ej: 111): ").strip()
    contexto  = input(f"  Contexto [{CONTEXTO_DEFAULT}]:  ").strip() or CONTEXTO_DEFAULT
    
    queries = [
        f"INSERT INTO ps_auths (id, auth_type, username, password) VALUES ('{ext_id}', 'userpass', '{ext_id}', '{password}');",
        f"INSERT INTO ps_aors (id, max_contacts, remove_existing) VALUES ('{ext_id}', 1, 'yes');",
        f"INSERT INTO ps_endpoints (id, transport, aors, auth, context, disallow, allow) VALUES ('{ext_id}', 'transport-udp', '{ext_id}', '{ext_id}', '{contexto}', 'all', 'ulaw,alaw');",
    ]
    
    for q in queries:
        run_query(q)
    
    print(f"  [OK] Usuario '{ext_id}' creado en DB.")

    if ext_num:
        añadir_extension_conf(ext_num, ext_id)

    if input("  ¿Recargar Asterisk? (s/n): ").lower() == "s":
        recargar_asterisk()

def listar_usuarios():
    print("\n── USUARIOS REGISTRADOS ──")
    res = run_query("SELECT e.id, a.password, e.context FROM ps_endpoints e JOIN ps_auths a ON e.id = a.id;")
    if res:
        print(res)
    else:
        print("  No hay usuarios.")

def eliminar_usuario():
    print("\n── ELIMINAR USUARIO ──")
    ext_id = input("  ID usuario a eliminar: ").strip()
    if not ext_id: return
    
    ext_num = input("  Número extensión en conf (vacío = omitir): ").strip()

    run_query(f"DELETE FROM ps_endpoints WHERE id='{ext_id}';")
    run_query(f"DELETE FROM ps_auths WHERE id='{ext_id}';")
    run_query(f"DELETE FROM ps_aors WHERE id='{ext_id}';")
    
    print(f"  [OK] Usuario '{ext_id}' eliminado de la DB.")
    
    if ext_num:
        eliminar_extension_conf(ext_num)

    if input("  ¿Recargar Asterisk? (s/n): ").lower() == "s":
        recargar_asterisk()

def recargar_asterisk():
    subprocess.run(["asterisk", "-rx", "dialplan reload"])
    subprocess.run(["asterisk", "-rx", "pjsip reload"])
    print("  [OK] Asterisk recargado.")

def menu():
    print("\n" + "="*45)
    print("   GESTOR ASTERISK PJSIP")
    print("="*45)
    print("  1. Añadir usuario")
    print("  2. Listar usuarios")
    print("  3. Eliminar usuario")
    print("  4. Ver extensions.conf")
    print("  5. Recargar Asterisk")
    print("  0. Salir")
    return input("\n  Opción: ").strip()

def main():
    global CFG
    cfg = cargar_config() or pedir_config()
    if not cfg: sys.exit(1)
    CFG.update(cfg)

    while True:
        op = menu()
        if op == "1": añadir_usuario()
        elif op == "2": listar_usuarios()
        elif op == "3": eliminar_usuario()
        elif op == "4": print("\n" + leer_conf())
        elif op == "5": recargar_asterisk()
        elif op == "0": break

if __name__ == "__main__":
    main()