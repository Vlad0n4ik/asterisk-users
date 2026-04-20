#!/usr/bin/env python3
"""
Gestor de usuarios Asterisk PJSIP
Uso: python3 asterisk_users.py
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
    print("  Primera vez que ejecutas el script.")
    print("  Introduce los datos de conexión a MariaDB.\n")

    host = input("  Host de MariaDB [localhost]: ").strip() or "localhost"
    user = input("  Usuario de MariaDB [root]:   ").strip() or "root"
    pwd  = input("  Contraseña de MariaDB:       ").strip()
    db   = input("  Nombre de la base de datos [asterisk]: ").strip() or "asterisk"

    cfg = {"host": host, "user": user, "password": pwd, "database": db}

    # Probar conexión antes de guardar
    print("\n  Probando conexión...")
    test = run_query_cfg("SELECT 1;", cfg)
    if test is None:
        print("  [!] No se pudo conectar. Revisa los datos e inténtalo de nuevo.")
        return None

    print("  [OK] Conexión exitosa.")
    guardar = input("  ¿Guardar esta configuración? (s/n): ").strip().lower()
    if guardar == "s":
        guardar_config(cfg)

    return cfg


def run_query_cfg(sql, cfg):
    """Ejecuta una query usando un dict de configuración."""
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


# Variable global de configuración
CFG = {}

def run_query(sql):
    return run_query_cfg(sql, CFG)


# ─── MENÚ ─────────────────────────────────────────────────────────────────────

def menu():
    print("\n" + "="*45)
    print("   GESTOR DE USUARIOS ASTERISK PJSIP")
    print("="*45)
    print("  1. Añadir usuario")
    print("  2. Listar usuarios")
    print("  3. Eliminar usuario")
    print("  4. Cambiar contraseña")
    print("  5. Ver extensions.conf")
    print("  6. Recargar Asterisk (dialplan + pjsip)")
    print("  7. Cambiar configuración de base de datos")
    print("  0. Salir")
    print("="*45)
    return input("  Elige una opción: ").strip()


# ─── EXTENSIONS.CONF ──────────────────────────────────────────────────────────

def leer_conf():
    if not os.path.exists(EXTENSIONS_CONF):
        return ""
    with open(EXTENSIONS_CONF, "r") as f:
        return f.read()


def guardar_conf(contenido):
    with open(EXTENSIONS_CONF, "w") as f:
        f.write(contenido)


def extension_existe(ext_num, contenido):
    patron = rf"exten\s*=>\s*{re.escape(ext_num)}\s*,"
    return bool(re.search(patron, contenido))


def añadir_extension_conf(ext_num, pjsip_id):
    contenido = leer_conf()
    nuevas_lineas = (
        f"exten => {ext_num},1,Dial(PJSIP/{pjsip_id})\n"
        f"exten => {ext_num},2,Hangup()\n"
    )

    if extension_existe(ext_num, contenido):
        print(f"  [!] La extensión {ext_num} ya existe en extensions.conf, no se modificó.")
        return

    seccion = f"[{CONTEXTO_DEFAULT}]"

    if seccion in contenido:
        # Buscar fin de la línea donde está [from-internal] e insertar después
        idx = contenido.index(seccion) + len(seccion)
        # Avanzar hasta el final de esa línea
        while idx < len(contenido) and contenido[idx] != "\n":
            idx += 1
        contenido = contenido[:idx] + "\n" + nuevas_lineas + contenido[idx:]
    else:
        # El contexto no existe, añadirlo al final
        if not contenido.endswith("\n"):
            contenido += "\n"
        contenido += f"\n[{CONTEXTO_DEFAULT}]\n{nuevas_lineas}"

    guardar_conf(contenido)
    print(f"  [OK] Extensión {ext_num} añadida en extensions.conf.")


def eliminar_extension_conf(ext_num):
    contenido = leer_conf()
    # re.MULTILINE para que .* no cruce líneas y capturar el \n al final
    patron = rf"^exten\s*=>\s*{re.escape(ext_num)}\s*,.*\n"
    nuevo = re.sub(patron, "", contenido, flags=re.MULTILINE)

    if nuevo == contenido:
        print(f"  [!] No se encontró la extensión {ext_num} en extensions.conf.")
        return

    guardar_conf(nuevo)
    print(f"  [OK] Extensión {ext_num} eliminada de extensions.conf.")


def ver_extensions():
    print("\n── EXTENSIONS.CONF ──")
    contenido = leer_conf()
    if not contenido:
        print(f"  No se encontró {EXTENSIONS_CONF}")
        return
    print()
    print(contenido)


# ─── BASE DE DATOS ────────────────────────────────────────────────────────────

def añadir_usuario():
    print("\n── AÑADIR USUARIO ──")
    ext_id = input("  Extensión / ID (ej: tel3):     ").strip()
    if not ext_id:
        print("  [!] La extensión no puede estar vacía.")
        return

    existe = run_query(f"SELECT id FROM ps_auths WHERE id='{ext_id}';")
    if existe:
        print(f"  [!] El usuario '{ext_id}' ya existe en la base de datos.")
        return

    password  = input("  Contraseña:                    ").strip()
    ext_num   = input("  Número de extensión (ej: 111): ").strip()
    contexto  = input(f"  Contexto [{CONTEXTO_DEFAULT}]:  ").strip() or CONTEXTO_DEFAULT
    transport = input("  Transport [transport-udp]:     ").strip() or "transport-udp"
    codecs    = input("  Codecs [ulaw,alaw]:            ").strip() or "ulaw,alaw"
    max_cont  = input("  Máx. contactos [1]:            ").strip() or "1"

    queries = [
        f"INSERT INTO ps_auths (id, auth_type, username, password) VALUES ('{ext_id}', 'userpass', '{ext_id}', '{password}');",
        f"INSERT INTO ps_aors (id, max_contacts, remove_existing) VALUES ('{ext_id}', {max_cont}, 'yes');",
        f"INSERT INTO ps_endpoints (id, transport, aors, auth, context, disallow, allow) VALUES ('{ext_id}', '{transport}', '{ext_id}', '{ext_id}', '{contexto}', 'all', '{codecs}');",
    ]
    for q in queries:
        run_query(q)
    print(f"  [OK] Usuario '{ext_id}' creado en base de datos.")

    if ext_num:
        añadir_extension_conf(ext_num, ext_id)

    recargar = input("  ¿Recargar Asterisk ahora? (s/n): ").strip().lower()
    if recargar == "s":
        recargar_asterisk()


def listar_usuarios():
    print("\n── USUARIOS REGISTRADOS ──")
    resultado = run_query(
        "SELECT e.id, a.username, a.password, e.context, e.allow "
        "FROM ps_endpoints e "
        "JOIN ps_auths a ON e.id = a.id "
        "ORDER BY e.id;"
    )
    if not resultado:
        print("  No hay usuarios o error de conexión.")
        return

    lineas = resultado.split("\n")
    if len(lineas) <= 1:
        print("  No hay usuarios creados.")
        return

    print(f"\n  {'ID':<12} {'Usuario':<12} {'Contraseña':<12} {'Contexto':<18} {'Codecs'}")
    print("  " + "-"*68)
    for linea in lineas[1:]:
        cols = linea.split("\t")
        if len(cols) >= 5:
            print(f"  {cols[0]:<12} {cols[1]:<12} {cols[2]:<12} {cols[3]:<18} {cols[4]}")


def eliminar_usuario():
    print("\n── ELIMINAR USUARIO ──")
    ext_id  = input("  ID del usuario a eliminar:                               ").strip()
    if not ext_id:
        return
    ext_num = input("  Número de extensión en extensions.conf (vacío = omitir): ").strip()

    confirmar = input(f"  ¿Seguro que quieres eliminar '{ext_id}'? (s/n): ").strip().lower()
    if confirmar != "s":
        print("  Cancelado.")
        return

    queries = [
        f"DELETE FROM ps_endpoints WHERE id='{ext_id}';",
        f"DELETE FROM ps_auths WHERE id='{ext_id}';",
        f"DELETE FROM ps_aors WHERE id='{ext_id}';",
        f"DELETE FROM ps_contacts WHERE endpoint='{ext_id}';",
    ]
    for q in queries:
        run_query(q)
    print(f"  [OK] Usuario '{ext_id}' eliminado de la base de datos.")

    if ext_num:
        eliminar_extension_conf(ext_num)

    recargar = input("  ¿Recargar Asterisk ahora? (s/n): ").strip().lower()
    if recargar == "s":
        recargar_asterisk()


def cambiar_password():
    print("\n── CAMBIAR CONTRASEÑA ──")
    ext_id = input("  ID del usuario: ").strip()
    if not ext_id:
        return

    existe = run_query(f"SELECT id FROM ps_auths WHERE id='{ext_id}';")
    if not existe:
        print(f"  [!] El usuario '{ext_id}' no existe.")
        return

    nueva = input("  Nueva contraseña: ").strip()
    if not nueva:
        return

    run_query(f"UPDATE ps_auths SET password='{nueva}' WHERE id='{ext_id}';")
    print(f"  [OK] Contraseña de '{ext_id}' actualizada.")

    recargar = input("  ¿Recargar Asterisk ahora? (s/n): ").strip().lower()
    if recargar == "s":
        recargar_asterisk()


def cambiar_configuracion():
    print("\n── CAMBIAR CONFIGURACIÓN DE BASE DE DATOS ──")
    print(f"  Configuración actual:")
    print(f"    Host:     {CFG['host']}")
    print(f"    Usuario:  {CFG['user']}")
    print(f"    Base de datos: {CFG['database']}")
    print()
    confirmar = input("  ¿Quieres introducir nuevos datos? (s/n): ").strip().lower()
    if confirmar != "s":
        return

    nueva_cfg = pedir_config()
    if nueva_cfg:
        CFG.update(nueva_cfg)


def recargar_asterisk():
    print("  Recargando dialplan...")
    r1 = subprocess.run(["asterisk", "-rx", "dialplan reload"], capture_output=True, text=True)
    print("  Recargando PJSIP...")
    r2 = subprocess.run(["asterisk", "-rx", "pjsip reload"], capture_output=True, text=True)
    if r1.returncode == 0 and r2.returncode == 0:
        print("  [OK] Asterisk recargado correctamente.")
    else:
        if r1.returncode != 0:
            print(f"  [ERROR] dialplan: {r1.stderr.strip()}")
        if r2.returncode != 0:
            print(f"  [ERROR] pjsip: {r2.stderr.strip()}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    global CFG

    cfg = cargar_config()

    if cfg:
        print(f"\n  Configuración cargada: {cfg['user']}@{cfg['host']}/{cfg['database']}")
        test = run_query_cfg("SELECT 1;", cfg)
        if test is None:
            print("  [!] No se pudo conectar con la configuración guardada.")
            cfg = pedir_config()
        else:
            print("  [OK] Conexión a MariaDB establecida.")
    else:
        cfg = pedir_config()

    if cfg is None:
        print("\n  No se pudo establecer conexión. Saliendo.")
        sys.exit(1)

    CFG.update(cfg)

    while True:
        opcion = menu()
        if opcion == "1":
            añadir_usuario()
        elif opcion == "2":
            listar_usuarios()
        elif opcion == "3":
            eliminar_usuario()
        elif opcion == "4":
            cambiar_password()
        elif opcion == "5":
            ver_extensions()
        elif opcion == "6":
            recargar_asterisk()
        elif opcion == "7":
            cambiar_configuracion()
        elif opcion == "0":
            print("\n  Hasta luego.\n")
            break
        else:
            print("  Opción no válida.")


if __name__ == "__main__":
    main()
