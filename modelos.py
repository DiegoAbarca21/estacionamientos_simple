"""
Clases del sistema: Estacionamiento y Reserva.
También incluye funciones pequeñas para trabajar con fechas y horas.
"""
from datetime import datetime, timedelta

FORMATO = "%Y-%m-%d %H:%M"          # formato de fechas en los CSV
BLOQUE = timedelta(minutes=30)       # el dataset trabaja en bloques de 30 minutos
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


# ---------------------------------------------------------------------------
# Funciones de apoyo para fechas
# ---------------------------------------------------------------------------
def texto_a_fecha(texto):
    """'2026-11-10 09:30' -> datetime. Devuelve None si el texto está vacío."""
    if not texto:
        return None
    return datetime.strptime(texto, FORMATO)


def fecha_a_texto(fecha):
    if fecha is None:
        return ""
    return fecha.strftime(FORMATO)


def inicio_de_bloque(fecha):
    """Redondea hacia abajo al bloque de 30 min (ej. 10:17 -> 10:00)."""
    minutos = 0 if fecha.minute < 30 else 30
    return fecha.replace(minute=minutos, second=0, microsecond=0)


def bloques(inicio, fin):
    """Lista con el inicio de cada bloque de 30 min entre inicio y fin."""
    lista = []
    actual = inicio_de_bloque(inicio)
    while actual < fin:
        lista.append(actual)
        actual = actual + BLOQUE
    return lista


def texto_periodo(inicio, fin):
    """Ej: 'mar 10/11 09:00-13:00'."""
    return f"{DIAS[inicio.weekday()]} {inicio:%d/%m %H:%M}-{fin:%H:%M}"


# ---------------------------------------------------------------------------
# Estacionamiento
# ---------------------------------------------------------------------------
class Estacionamiento:
    """Un estacionamiento del edificio y su disponibilidad.

    La disponibilidad se guarda como conjuntos de bloques de 30 minutos:
    - bloques_liberados: bloques que el propietario ofrece a terceros.
    - bloques_bloqueados: bloques que el propietario se reservó para sí.
    Un bloque nunca está en ambos conjuntos a la vez.
    """

    def __init__(self, id, propietario):
        self.id = id
        self.propietario = propietario
        self.bloques_liberados = set()
        self.bloques_bloqueados = set()

    def liberar(self, inicio, fin):
        for b in bloques(inicio, fin):
            self.bloques_liberados.add(b)
            self.bloques_bloqueados.discard(b)   # la última decisión del dueño manda

    def bloquear(self, inicio, fin):
        for b in bloques(inicio, fin):
            self.bloques_bloqueados.add(b)
            self.bloques_liberados.discard(b)

    def esta_liberado(self, inicio, fin):
        """True si TODOS los bloques del período están liberados (RN03)."""
        return all(b in self.bloques_liberados for b in bloques(inicio, fin))

    def esta_bloqueado(self, inicio, fin):
        return any(b in self.bloques_bloqueados for b in bloques(inicio, fin))

    def estado_en(self, momento):
        b = inicio_de_bloque(momento)
        if b in self.bloques_bloqueados:
            return "BLOQUEADO"
        if b in self.bloques_liberados:
            return "LIBERADO"
        return "NO OFRECIDO"


# ---------------------------------------------------------------------------
# Reserva
# ---------------------------------------------------------------------------
# Estados posibles de una reserva
PENDIENTE = "PENDIENTE"      # creada; el estacionamiento queda retenido hasta que el admin la asigne
ASIGNADA = "ASIGNADA"        # el administrador confirmó el estacionamiento
AFECTADA = "AFECTADA"        # el propietario bloqueó su espacio: falta reasignar o compensar
FINALIZADA = "FINALIZADA"    # terminó el período
LIBERADA = "LIBERADA"        # el cliente se fue antes
CANCELADA = "CANCELADA"      # el cliente canceló antes del inicio
COMPENSADA = "COMPENSADA"    # anulada por contingencia sin alternativa

COLUMNAS_RESERVA = ["id", "cliente", "patente", "estacionamiento", "inicio", "fin", "estado",
                    "tipo", "serie", "descuento", "monto", "fin_real", "monto_cobrado",
                    "credito_usado", "pago_propietario", "comision_operador", "compensacion",
                    "reserva_origen", "creada"]


class Reserva:
    def __init__(self, id, cliente, patente, estacionamiento, inicio, fin, monto,
                 estado=PENDIENTE, tipo="PUNTUAL", serie="", descuento=0.0):
        self.id = id
        self.cliente = cliente
        self.patente = patente
        self.estacionamiento = estacionamiento
        self.inicio = inicio
        self.fin = fin
        self.monto = monto                  # precio acordado al reservar
        self.estado = estado
        self.tipo = tipo                    # PUNTUAL o RECURRENTE
        self.serie = serie                  # id de la serie si es recurrente
        self.descuento = descuento
        # Datos que se completan al cerrar la reserva
        self.fin_real = None
        self.monto_cobrado = 0
        self.credito_usado = 0
        self.pago_propietario = 0
        self.comision_operador = 0
        self.compensacion = 0
        self.reserva_origen = ""            # si nació de dividir una reasignación en curso
        self.creada = None

    def ocupa_estacionamiento(self):
        """Solo PENDIENTE y ASIGNADA ocupan su estacionamiento (RN02)."""
        return self.estado in (PENDIENTE, ASIGNADA)

    def esta_vigente(self):
        return self.estado in (PENDIENTE, ASIGNADA, AFECTADA)

    def se_cruza_con(self, inicio, fin):
        return self.inicio < fin and inicio < self.fin

    def __str__(self):
        return (f"{self.id} | {texto_periodo(self.inicio, self.fin)} | {self.estacionamiento} | "
                f"{self.patente} | {self.estado} | ${self.monto:,}".replace(",", "."))

    # --- conversión a/desde una fila de CSV --------------------------------
    def a_fila(self):
        return {
            "id": self.id, "cliente": self.cliente, "patente": self.patente,
            "estacionamiento": self.estacionamiento, "inicio": fecha_a_texto(self.inicio),
            "fin": fecha_a_texto(self.fin), "estado": self.estado, "tipo": self.tipo,
            "serie": self.serie, "descuento": self.descuento, "monto": self.monto,
            "fin_real": fecha_a_texto(self.fin_real), "monto_cobrado": self.monto_cobrado,
            "credito_usado": self.credito_usado, "pago_propietario": self.pago_propietario,
            "comision_operador": self.comision_operador, "compensacion": self.compensacion,
            "reserva_origen": self.reserva_origen, "creada": fecha_a_texto(self.creada),
        }

    @staticmethod
    def desde_fila(f):
        r = Reserva(f["id"], f["cliente"], f["patente"], f["estacionamiento"],
                    texto_a_fecha(f["inicio"]), texto_a_fecha(f["fin"]), int(f["monto"]),
                    f["estado"], f["tipo"], f["serie"], float(f["descuento"]))
        r.fin_real = texto_a_fecha(f["fin_real"])
        r.monto_cobrado = int(f["monto_cobrado"])
        r.credito_usado = int(f["credito_usado"])
        r.pago_propietario = int(f["pago_propietario"])
        r.comision_operador = int(f["comision_operador"])
        r.compensacion = int(f["compensacion"])
        r.reserva_origen = f["reserva_origen"]
        r.creada = texto_a_fecha(f["creada"])
        return r
