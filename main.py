"""
Sistema de Gestión de Estacionamientos Particulares — Entrega 2 (HEI ICIF, USS)
Versión simplificada: solo biblioteca estándar de Python.

Ejecutar:  python main.py
"""
from datetime import datetime, timedelta

import datos
from modelos import AFECTADA, ASIGNADA, DIAS, PENDIENTE
from sistema import Sistema


# ---------------------------------------------------------------------------
# Funciones para pedir datos por consola
# ---------------------------------------------------------------------------
def pedir(texto, defecto=""):
    valor = input(f"  {texto}{f' [{defecto}]' if defecto else ''}: ").strip()
    return valor or defecto


def pedir_fecha(texto):
    """Acepta 'hoy', 'mañana' o dd-mm-aaaa."""
    while True:
        valor = pedir(f"{texto} (hoy / mañana / dd-mm-aaaa)", "hoy").lower()
        hoy = datetime.now().date()
        if valor == "hoy":
            return hoy
        if valor in ("mañana", "manana"):
            return hoy + timedelta(days=1)
        try:
            return datetime.strptime(valor, "%d-%m-%Y").date()
        except ValueError:
            print("  Fecha no válida.")


def pedir_hora(texto, defecto):
    while True:
        try:
            return datetime.strptime(pedir(f"{texto} (HH:MM)", defecto), "%H:%M").time()
        except ValueError:
            print("  Hora no válida. Ejemplo: 09:30")


def pedir_periodo():
    dia = pedir_fecha("Fecha")
    inicio = pedir_hora("Hora de inicio", "09:00")
    fin = pedir_hora("Hora de término", "13:00")
    return datetime.combine(dia, inicio), datetime.combine(dia, fin)


def pedir_dias():
    """Acepta 'L-V' o una lista como 'lun,mie,vie'."""
    valor = pedir("Días (L-V o ej. lun,mie,vie)", "L-V").lower()
    if valor == "l-v":
        return [0, 1, 2, 3, 4]
    nombres = {"lun": 0, "mar": 1, "mie": 2, "mié": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
    return sorted({nombres[d.strip()[:3]] for d in valor.split(",") if d.strip()[:3] in nombres})


def mostrar(reservas):
    if not reservas:
        print("  (no hay reservas)")
    for r in reservas:
        print("  " + str(r))


def pesos(valor):
    return f"${valor:,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Menú del PROPIETARIO
# ---------------------------------------------------------------------------
def menu_propietario(s):
    est_id = pedir("Número de estacionamiento (ej. E04)").upper()
    if est_id not in s.estacionamientos:
        print("  No existe ese estacionamiento.")
        return
    est = s.estacionamientos[est_id]
    propietario = est.propietario
    while True:
        print(f"\n--- PROPIETARIO {propietario} (estacionamiento {est_id}) ---")
        print("1. Ver estado y reservas de mi estacionamiento")
        print("2. Liberar (ofrecer) mi estacionamiento")
        print("3. Bloquear (lo voy a usar yo)")
        print("4. Definir horario semanal recurrente   [propia]")
        print("0. Volver")
        op = pedir("Opción")
        try:
            if op == "1":
                print(f"  Estado ahora: {est.estado_en(s.ahora())}")
                mostrar([r for r in s.reservas if r.estacionamiento == est_id and r.esta_vigente()])
                ganado = sum(r.pago_propietario for r in s.reservas if r.estacionamiento == est_id)
                print(f"  Ingresos acumulados (80 %): {pesos(ganado)}")
            elif op == "2":
                inicio, fin = pedir_periodo()
                bajo = s.liberar(propietario, est_id, inicio, fin)
                print("  Listo: estacionamiento liberado.")
                if bajo:
                    print(f"  Aviso: {bajo} bloques tienen disponibilidad histórica bajo 80 % "
                          "y no se ofrecerán a clientes.")
            elif op == "3":
                inicio, fin = pedir_periodo()
                afectadas = s.reservas_afectadas(propietario, est_id, inicio, fin)
                if afectadas:
                    print("  Ojo: hay reservas en ese período:")
                    mostrar(afectadas)
                    print("  Usted tiene prioridad; el administrador reasignará o compensará al cliente.")
                    if pedir("¿Confirmar bloqueo? (s/n)", "n").lower() != "s":
                        continue
                motivo = pedir("Motivo", "uso personal")
                resultado = s.bloquear(propietario, est_id, inicio, fin, motivo)
                print("  Listo: estacionamiento bloqueado.")
                for r, n in resultado:
                    print(f"  {r.id} quedó AFECTADA ({n} estacionamientos alternativos disponibles).")
            elif op == "4":
                print("  Según el dataset, usted suele estar fuera (≥ 80 % de las semanas):")
                for d in range(5):
                    tramos = s.sugerir_horario(est_id, d)
                    texto = ", ".join(f"{a:%H:%M}-{b:%H:%M}" for a, b in tramos) or "sin tramos sugeridos"
                    print(f"   {DIAS[d]}: {texto}")
                dias = pedir_dias()
                h1 = pedir_hora("Hora inicio", "09:00")
                h2 = pedir_hora("Hora término", "17:00")
                desde = pedir_fecha("Desde")
                hasta = pedir_fecha("Hasta")
                liberadas, omitidas = s.horario_recurrente(propietario, est_id, dias, h1, h2, desde, hasta)
                print(f"  Listo: {liberadas} h liberadas.")
                if omitidas:
                    print(f"  Se respetaron sus bloqueos: {omitidas} h no se liberaron.")
            elif op == "0":
                return
        except ValueError as error:
            print(f"  ERROR: {error}")


# ---------------------------------------------------------------------------
# Menú del CLIENTE
# ---------------------------------------------------------------------------
def menu_cliente(s):
    cliente = pedir("ID de cliente (ej. C01)").upper()
    if cliente not in s.clientes:
        print("  No existe ese cliente.")
        return
    while True:
        datos_cliente = s.clientes[cliente]
        print(f"\n--- CLIENTE {cliente} {datos_cliente['nombre']} ({datos_cliente['patente']}) "
              f"- crédito {pesos(datos_cliente['credito'])} ---")
        print("1. Ver mis reservas")
        print("2. Reservar")
        print("3. Cancelar una reserva")
        print("4. Liberar anticipadamente (me voy antes)")
        print("5. Reserva recurrente   [propia]")
        print("0. Volver")
        op = pedir("Opción")
        try:
            if op == "1":
                mostrar([r for r in s.reservas if r.cliente == cliente])
            elif op == "2":
                inicio, fin = pedir_periodo()
                s.validar_periodo(inicio, fin)
                opciones = s.opciones(inicio, fin)[:3]
                elegido = ""
                if opciones:
                    print("  Opciones (menor riesgo primero):")
                    for i, (est_id, holgura) in enumerate(opciones, 1):
                        print(f"   {i}. {est_id} - el dueño suele seguir fuera {holgura} h más")
                    n = pedir("Elija una opción", "1")
                    if n.isdigit() and 1 <= int(n) <= len(opciones):
                        elegido = opciones[int(n) - 1][0]
                r = s.reservar(cliente, inicio, fin, pedir("Patente", datos_cliente["patente"]), elegido)
                print(f"  Reserva creada: {r}")
            elif op == "3":
                mostrar([r for r in s.reservas if r.cliente == cliente and r.esta_vigente()])
                r = s.buscar_reserva(pedir("ID de la reserva (ej. R0003)").upper(), cliente)
                if r.serie and pedir(f"Es parte de la serie {r.serie}. ¿Cancelar toda la serie? (s/n)", "n") == "s":
                    print(f"  Serie cancelada. Cargo total: {pesos(s.cancelar_serie(cliente, r.serie))}")
                else:
                    print(f"  Reserva cancelada. Cargo: {pesos(s.cancelar(cliente, r.id))}")
            elif op == "4":
                cargo = s.liberar_reserva(cliente, pedir("ID de la reserva en curso").upper())
                print(f"  Estacionamiento liberado. Se cobran solo los bloques usados: {pesos(cargo)}")
            elif op == "5":
                dias = pedir_dias()
                h1 = pedir_hora("Hora inicio", "09:00")
                h2 = pedir_hora("Hora término", "13:00")
                desde = pedir_fecha("Desde")
                hasta = pedir_fecha("Hasta")
                creadas = s.reserva_recurrente(cliente, dias, h1, h2, desde, hasta)
                mostrar(creadas)
                total = sum(r.monto for r in creadas)
                print(f"  Serie creada: {len(creadas)} reservas, descuento {creadas[0].descuento:.0%}, "
                      f"total {pesos(total)}")
            elif op == "0":
                return
        except ValueError as error:
            print(f"  ERROR: {error}")


# ---------------------------------------------------------------------------
# Menú del ADMINISTRADOR
# ---------------------------------------------------------------------------
def menu_administrador(s):
    while True:
        pendientes = [r for r in s.reservas if r.estado == PENDIENTE]
        afectadas = [r for r in s.reservas if r.estado == AFECTADA]
        print("\n--- ADMINISTRADOR ---")
        print(f"1. Asignar reservas pendientes ({len(pendientes)})")
        print("2. Reasignar una reserva")
        print(f"3. Gestionar contingencias ({len(afectadas)} afectadas)   [propia]")
        print("4. Ver estado de todos los estacionamientos ahora")
        print("5. Ver últimos eventos del historial")
        print("0. Volver")
        op = pedir("Opción")
        try:
            if op == "1":
                mostrar(pendientes)
                if pendientes:
                    rid = pedir("ID de la reserva (o T para asignar todas al sugerido)").upper()
                    if rid == "T":
                        for r in pendientes:
                            s.asignar(r.id)
                        print(f"  {len(pendientes)} reservas asignadas.")
                    else:
                        r = s.buscar_reserva(rid)
                        print(f"  Disponibles: {', '.join(s.alternativas(r)[:6])}")
                        r = s.asignar(rid, pedir("Estacionamiento", r.estacionamiento).upper())
                        print(f"  Asignada: {r}")
            elif op == "2":
                mostrar([r for r in s.reservas if r.estado in (ASIGNADA, AFECTADA) and r.fin > s.ahora()])
                r = s.buscar_reserva(pedir("ID de la reserva").upper())
                alternativas = s.alternativas(r)
                print(f"  Disponibles (menor riesgo primero): {', '.join(alternativas[:6]) or 'ninguno'}")
                destino = pedir("Nuevo estacionamiento", alternativas[0] if alternativas else "").upper()
                nueva = s.reasignar(r.id, destino, pedir("Motivo", "decisión operativa"))
                print(f"  Reasignada: {nueva}")
            elif op == "3":
                if not afectadas:
                    print("  No hay contingencias.")
                    continue
                for r in afectadas:
                    alternativas = s.alternativas(r)
                    accion = f"puede reasignarse a {alternativas[0]}" if alternativas else "SIN alternativa: compensar"
                    print(f"  {r} -> {accion}")
                print("  Regla: primero reasignar; compensar (crédito 50 %) solo si no hay alternativa.")
                sub = pedir("a) Resolver todas   b) Compensar una   c) Volver", "a").lower()
                if sub == "a":
                    for linea in s.resolver_contingencias():
                        print("  " + linea)
                elif sub == "b":
                    credito = s.compensar(pedir("ID de la reserva").upper())
                    print(f"  Compensada: crédito de {pesos(credito)} para el cliente.")
            elif op == "4":
                conteo = {}
                for est in s.estacionamientos.values():
                    estado = est.estado_en(s.ahora())
                    if s.reservas_que_ocupan(est.id, s.ahora(), s.ahora() + timedelta(minutes=1)):
                        estado = "OCUPADO"
                    conteo.setdefault(estado, []).append(est.id)
                for estado, ids in conteo.items():
                    print(f"  {estado:12} {len(ids):2}: {' '.join(ids)}")
            elif op == "5":
                for f in datos.leer_csv("historial.csv")[-15:]:
                    print(f"  {f['fecha_hora']} | {f['tipo']:22} | {f['reserva']:5} | "
                          f"{f['estacionamiento']:3} | {f['actor']:13} | {f['detalle']}")
            elif op == "0":
                return
        except ValueError as error:
            print(f"  ERROR: {error}")


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
def main():
    s = Sistema()
    while True:
        cambios = s.actualizar_estados()
        if cambios:
            print(f"\n  (Actualización automática: {cambios} reservas cambiaron de estado)")
        print(f"\n===== GESTIÓN DE ESTACIONAMIENTOS - {s.ahora():%d-%m-%Y %H:%M} =====")
        print("1. Propietario")
        print("2. Cliente")
        print("3. Administrador")
        print("0. Salir")
        op = pedir("Opción")
        if op == "1":
            menu_propietario(s)
        elif op == "2":
            menu_cliente(s)
        elif op == "3":
            menu_administrador(s)
        elif op == "0":
            print("  Datos guardados. ¡Hasta luego!")
            break


if __name__ == "__main__":
    main()
