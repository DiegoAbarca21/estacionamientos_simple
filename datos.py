"""
Lectura y escritura de archivos CSV (persistencia del sistema).

Archivos en la carpeta datos/:
  dataset_estacionamientos.csv  dataset de la Entrega 1 (solo se lee)
  clientes.csv                  clientes registrados y su crédito
  liberaciones.csv              períodos que cada propietario ofrece
  bloqueos.csv                  períodos que cada propietario se reservó
  reservas.csv                  estado actual de cada reserva
  historial.csv                 TODOS los eventos con fecha y hora (para la Entrega 3)
"""
import csv
import os
from datetime import datetime

from modelos import BLOQUE, COLUMNAS_RESERVA, Estacionamiento, Reserva, fecha_a_texto, texto_a_fecha

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")

COLUMNAS_HISTORIAL = ["fecha_hora", "tipo", "actor", "reserva", "estacionamiento",
                      "estacionamiento_anterior", "propietario", "cliente", "inicio", "fin",
                      "estado", "monto", "detalle"]


def ruta(nombre):
    return os.path.join(CARPETA, nombre)


def existe(nombre):
    return os.path.exists(ruta(nombre))


def leer_csv(nombre):
    """Devuelve una lista de diccionarios (vacía si el archivo no existe)."""
    if not existe(nombre):
        return []
    with open(ruta(nombre), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def escribir_csv(nombre, columnas, filas):
    """Reescribe el archivo completo con las filas indicadas."""
    with open(ruta(nombre), "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(filas)


def agregar_fila(nombre, columnas, fila):
    """Agrega una fila al final (se usa para el historial, que nunca se borra)."""
    nuevo = not existe(nombre)
    with open(ruta(nombre), "a", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas)
        if nuevo:
            escritor.writeheader()
        escritor.writerow(fila)


# ---------------------------------------------------------------------------
# Dataset de la Entrega 1
# ---------------------------------------------------------------------------
def leer_dataset():
    """Lee el dataset y calcula el perfil histórico.

    Devuelve (lista de ids de estacionamientos, perfil), donde
    perfil[(estacionamiento, dia_semana, "HH:MM")] = proporción de semanas en
    que estuvo disponible (0 = nunca, 1 = las 4 semanas).
    """
    filas = leer_csv("dataset_estacionamientos.csv")
    ids = [col for col in filas[0].keys() if col.startswith("E")]
    sumas = {}
    cuentas = {}
    for fila in filas:
        momento = datetime.strptime(fila["FechaHora"], "%Y-%m-%d %H:%M")
        for est in ids:
            clave = (est, momento.weekday(), fila["Hora"])
            sumas[clave] = sumas.get(clave, 0) + int(fila[est])
            cuentas[clave] = cuentas.get(clave, 0) + 1
    perfil = {}
    for clave in sumas:
        perfil[clave] = sumas[clave] / cuentas[clave]
    return ids, perfil


# ---------------------------------------------------------------------------
# Estacionamientos (liberaciones y bloqueos)
# ---------------------------------------------------------------------------
def bloques_a_periodos(conjunto):
    """Agrupa bloques consecutivos en períodos (inicio, fin) para guardarlos."""
    periodos = []
    for b in sorted(conjunto):
        if periodos and periodos[-1][1] == b:
            periodos[-1][1] = b + BLOQUE          # extiende el período anterior
        else:
            periodos.append([b, b + BLOQUE])
    return periodos


def cargar_estacionamientos(ids):
    estacionamientos = {}
    for est_id in ids:
        # El estacionamiento E07 pertenece al propietario P07
        estacionamientos[est_id] = Estacionamiento(est_id, "P" + est_id[1:])
    for f in leer_csv("liberaciones.csv"):
        estacionamientos[f["estacionamiento"]].liberar(texto_a_fecha(f["inicio"]), texto_a_fecha(f["fin"]))
    for f in leer_csv("bloqueos.csv"):
        estacionamientos[f["estacionamiento"]].bloquear(texto_a_fecha(f["inicio"]), texto_a_fecha(f["fin"]))
    return estacionamientos


def guardar_estacionamientos(estacionamientos):
    columnas = ["estacionamiento", "propietario", "inicio", "fin"]
    liberaciones, bloqueos = [], []
    for est in estacionamientos.values():
        for inicio, fin in bloques_a_periodos(est.bloques_liberados):
            liberaciones.append({"estacionamiento": est.id, "propietario": est.propietario,
                                 "inicio": fecha_a_texto(inicio), "fin": fecha_a_texto(fin)})
        for inicio, fin in bloques_a_periodos(est.bloques_bloqueados):
            bloqueos.append({"estacionamiento": est.id, "propietario": est.propietario,
                             "inicio": fecha_a_texto(inicio), "fin": fecha_a_texto(fin)})
    escribir_csv("liberaciones.csv", columnas, liberaciones)
    escribir_csv("bloqueos.csv", columnas, bloqueos)


# ---------------------------------------------------------------------------
# Reservas y clientes
# ---------------------------------------------------------------------------
def cargar_reservas():
    return [Reserva.desde_fila(f) for f in leer_csv("reservas.csv")]


def guardar_reservas(reservas):
    escribir_csv("reservas.csv", COLUMNAS_RESERVA, [r.a_fila() for r in reservas])


def cargar_clientes():
    """Diccionario {id: {"nombre": ..., "patente": ..., "credito": int}}."""
    clientes = {}
    for f in leer_csv("clientes.csv"):
        clientes[f["id"]] = {"nombre": f["nombre"], "patente": f["patente"], "credito": int(f["credito"])}
    return clientes


def guardar_clientes(clientes):
    filas = [{"id": cid, "nombre": c["nombre"], "patente": c["patente"], "credito": c["credito"]}
             for cid, c in clientes.items()]
    escribir_csv("clientes.csv", ["id", "nombre", "patente", "credito"], filas)


def registrar_evento(fila):
    agregar_fila("historial.csv", COLUMNAS_HISTORIAL, fila)
