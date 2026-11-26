"""
Clase Sistema: contiene los datos en memoria y todas las reglas de negocio,
organizadas por tipo de usuario (propietario, cliente y administrador).

Cuando una operación no cumple una regla se lanza ValueError con un mensaje
para el usuario, ANTES de modificar nada: así los datos nunca quedan a medias.
"""
import re
from datetime import datetime, timedelta

import datos
from modelos import (AFECTADA, ASIGNADA, BLOQUE, CANCELADA, COMPENSADA, DIAS, FINALIZADA,
                     LIBERADA, PENDIENTE, Reserva, bloques, fecha_a_texto, inicio_de_bloque)

# --- Parámetros del negocio ---------------------------------------------------
TARIFA_BLOQUE = 500             # $1.000 por hora = $500 por bloque de 30 min (Entrega 1)
PORCENTAJE_PROPIETARIO = 0.80   # reparto 80 % propietario / 20 % operador (Entrega 1)
UMBRAL_OFERTA = 0.80            # disponibilidad histórica mínima por bloque (Entrega 1)
HORAS_CANCELACION_GRATIS = 2    # cancelar con 2 h o más de anticipación no cuesta nada
RECARGO_CANCELACION = 0.50      # si se cancela tarde se cobra el 50 %
DESCUENTO_RECURRENTE = 0.10     # 10 % de descuento en series de 4 o más reservas
PORCENTAJE_COMPENSACION = 0.50  # crédito al cliente si pierde su reserva sin alternativa
MAX_HORAS_RESERVA = 12
SEMANAS_CARGA_INICIAL = 4       # semanas de horario que se generan desde el dataset


class Sistema:

    def __init__(self):
        self.ids, self.perfil = datos.leer_dataset()
        self.estacionamientos = datos.cargar_estacionamientos(self.ids)
        self.reservas = datos.cargar_reservas()
        self.clientes = datos.cargar_clientes()
        if not datos.existe("liberaciones.csv"):
            self.carga_inicial()

    # =======================================================================
    # Apoyo general
    # =======================================================================
    def ahora(self):
        return datetime.now().replace(second=0, microsecond=0)

    def guardar(self):
        datos.guardar_estacionamientos(self.estacionamientos)
        datos.guardar_reservas(self.reservas)
        datos.guardar_clientes(self.clientes)

    def registrar(self, tipo, actor, reserva=None, estacionamiento="", inicio=None, fin=None,
                  monto="", detalle="", anterior="", cliente=""):
        """Agrega un evento al historial (base de los indicadores de la Entrega 3)."""
        if reserva is not None:
            estacionamiento = reserva.estacionamiento
            inicio, fin = reserva.inicio, reserva.fin
        propietario = self.estacionamientos[estacionamiento].propietario if estacionamiento else ""
        datos.registrar_evento({
            "fecha_hora": fecha_a_texto(self.ahora()), "tipo": tipo, "actor": actor,
            "reserva": reserva.id if reserva else "", "estacionamiento": estacionamiento,
            "estacionamiento_anterior": anterior, "propietario": propietario,
            "cliente": reserva.cliente if reserva else cliente, "inicio": fecha_a_texto(inicio),
            "fin": fecha_a_texto(fin), "estado": reserva.estado if reserva else "",
            "monto": monto, "detalle": detalle})

    def validar_periodo(self, inicio, fin, max_horas=None):
        if fin <= inicio:
            raise ValueError("La hora de término debe ser posterior a la de inicio.")
        if inicio.minute not in (0, 30) or fin.minute not in (0, 30):
            raise ValueError("Use horas en punto o y media (bloques de 30 min).")
        if inicio < inicio_de_bloque(self.ahora()):
            raise ValueError("El período no puede comenzar en el pasado.")
        if max_horas and (fin - inicio) > timedelta(hours=max_horas):
            raise ValueError(f"El período no puede superar {max_horas} horas.")

    def buscar_estacionamiento(self, est_id, propietario=None):
        if est_id not in self.estacionamientos:
            raise ValueError(f"No existe el estacionamiento {est_id}.")
        est = self.estacionamientos[est_id]
        if propietario and est.propietario != propietario:
            raise ValueError(f"El estacionamiento {est_id} no pertenece a {propietario}.")
        return est

    def buscar_reserva(self, reserva_id, cliente=None):
        for r in self.reservas:
            if r.id == reserva_id:
                if cliente and r.cliente != cliente:
                    raise ValueError("La reserva no pertenece a este cliente.")
                return r
        raise ValueError(f"No existe la reserva {reserva_id}.")

    def nuevo_id_reserva(self):
        return f"R{len(self.reservas) + 1:04d}"

    # =======================================================================
    # Disponibilidad (RN02, RN03 y política de oferta)
    # =======================================================================
    def reservas_que_ocupan(self, est_id, inicio, fin, ignorar=None):
        """Reservas PENDIENTES o ASIGNADAS de ese estacionamiento que se cruzan con el período."""
        return [r for r in self.reservas
                if r.estacionamiento == est_id and r.ocupa_estacionamiento()
                and r.se_cruza_con(inicio, fin) and r is not ignorar]

    def historial_minimo(self, est_id, inicio, fin):
        """Menor disponibilidad histórica entre los bloques del período.
        None si el dataset no tiene datos (fines de semana o de noche)."""
        valores = []
        for b in bloques(inicio, fin):
            clave = (est_id, b.weekday(), b.strftime("%H:%M"))
            if clave in self.perfil:
                valores.append(self.perfil[clave])
        return min(valores) if valores else None

    def holgura(self, est_id, fin):
        """Horas que el propietario suele seguir fuera DESPUÉS del término
        (máximo 3). Más holgura = menos riesgo de que vuelva antes."""
        horas = 0.0
        momento = fin
        while horas < 3 and self.perfil.get((est_id, momento.weekday(), momento.strftime("%H:%M")), 0) >= UMBRAL_OFERTA:
            horas += 0.5
            momento += BLOQUE
        return horas

    def motivo_no_disponible(self, est_id, inicio, fin, ignorar=None):
        """Devuelve "" si el estacionamiento sirve; si no, la razón.
        Orden de la Entrega 1: propietario -> reservas existentes -> historial."""
        est = self.estacionamientos[est_id]
        if est.esta_bloqueado(inicio, fin):
            return "bloqueado por el propietario"
        if not est.esta_liberado(inicio, fin):
            return "no liberado por el propietario"
        if self.reservas_que_ocupan(est_id, inicio, fin, ignorar):
            return "ya tiene una reserva en ese horario"
        minimo = self.historial_minimo(est_id, inicio, fin)
        if minimo is not None and minimo < UMBRAL_OFERTA:
            return "bajo el umbral histórico de 80 %"
        return ""

    def opciones(self, inicio, fin, ignorar=None, excluir=""):
        """Estacionamientos disponibles, del menor al mayor riesgo (más holgura primero)."""
        lista = []
        for est_id in self.ids:
            if est_id != excluir and self.motivo_no_disponible(est_id, inicio, fin, ignorar) == "":
                lista.append((est_id, self.holgura(est_id, fin)))
        lista.sort(key=lambda opcion: -opcion[1])   # sort es estable: empates quedan por id
        return lista

    # =======================================================================
    # Cobros
    # =======================================================================
    def precio(self, inicio, fin, descuento=0.0):
        return round(len(bloques(inicio, fin)) * TARIFA_BLOQUE * (1 - descuento))

    def cobrar(self, reserva, monto, nuevo_estado):
        """Cierra la reserva cobrando `monto`: usa primero el crédito del cliente
        y reparte 80/20. El crédito lo pone el operador, no el propietario."""
        cliente = self.clientes[reserva.cliente]
        credito = min(cliente["credito"], monto)
        cliente["credito"] -= credito
        reserva.monto_cobrado = monto
        reserva.credito_usado = credito
        reserva.pago_propietario = round(monto * PORCENTAJE_PROPIETARIO)
        reserva.comision_operador = monto - reserva.pago_propietario
        reserva.estado = nuevo_estado

    # =======================================================================
    # Carga inicial desde el dataset
    # =======================================================================
    def carga_inicial(self):
        """Primera ejecución: cada propietario ofrece su estacionamiento en los
        tramos en que el dataset muestra que siempre está fuera, durante las
        próximas semanas (es el mismo horario que sugiere la opción del menú)."""
        hoy = self.ahora().date()
        for est_id in self.ids:
            for dia_semana in range(5):
                tramos = self.sugerir_horario(est_id, dia_semana)
                if not tramos:
                    continue
                desde, hasta = max(tramos, key=lambda t: t[1] - t[0])   # el tramo más largo
                if hasta.time() <= desde.time():
                    continue                                           # (tramo que llega a medianoche)
                for d in range(SEMANAS_CARGA_INICIAL * 7):
                    dia = hoy + timedelta(days=d)
                    if dia.weekday() == dia_semana:
                        self.estacionamientos[est_id].liberar(datetime.combine(dia, desde.time()),
                                                              datetime.combine(dia, hasta.time()))
        self.registrar("CARGA_INICIAL", "sistema",
                       detalle=f"horarios del dataset para {SEMANAS_CARGA_INICIAL} semanas")
        self.guardar()

    # =======================================================================
    # PROPIETARIO
    # =======================================================================
    def liberar(self, propietario, est_id, inicio, fin):
        """[Obligatoria] Ofrece el estacionamiento en un período.
        Devuelve cuántos bloques quedan bajo el umbral (no se ofrecerán)."""
        est = self.buscar_estacionamiento(est_id, propietario)
        self.validar_periodo(inicio, fin)
        est.liberar(inicio, fin)
        bajo_umbral = sum(1 for b in bloques(inicio, fin)
                          if self.perfil.get((est_id, b.weekday(), b.strftime("%H:%M")), 1) < UMBRAL_OFERTA)
        self.registrar("LIBERACION", propietario, estacionamiento=est_id, inicio=inicio, fin=fin,
                       detalle=f"{bajo_umbral} bloques bajo el umbral")
        self.guardar()
        return bajo_umbral

    def reservas_afectadas(self, propietario, est_id, inicio, fin):
        """Para avisar ANTES de bloquear qué reservas se verían afectadas."""
        self.buscar_estacionamiento(est_id, propietario)
        return self.reservas_que_ocupan(est_id, inicio, fin)

    def bloquear(self, propietario, est_id, inicio, fin, motivo):
        """[Obligatoria] El propietario recupera su espacio.
        RN01: el bloqueo SIEMPRE se aplica. Las reservas de ese período quedan
        AFECTADAS para que el administrador las reasigne o compense.
        Devuelve una lista (reserva, cantidad de alternativas)."""
        est = self.buscar_estacionamiento(est_id, propietario)
        self.validar_periodo(inicio, fin)
        if not motivo.strip():
            raise ValueError("Indique el motivo del bloqueo.")
        afectadas = self.reservas_que_ocupan(est_id, inicio, fin)
        est.bloquear(inicio, fin)
        self.registrar("BLOQUEO", propietario, estacionamiento=est_id, inicio=inicio, fin=fin, detalle=motivo)
        resultado = []
        for r in afectadas:
            r.estado = AFECTADA
            aviso = (r.inicio - self.ahora()).total_seconds() / 3600
            self.registrar("AFECTADA_POR_BLOQUEO", propietario, r,
                           detalle=f"{motivo}; aviso de {aviso:.1f} h antes del inicio")
            resultado.append((r, len(self.alternativas(r))))
        self.guardar()
        return resultado

    def sugerir_horario(self, est_id, dia_semana):
        """[Apoyo a la propia] Tramos de 2 h o más en que el dataset muestra
        disponibilidad >= 80 %. Devuelve una lista de (desde, hasta) como datetime."""
        tramos = []
        inicio_tramo = None
        hora = datetime(2000, 1, 1, 6, 0)
        fin_dia = datetime(2000, 1, 2, 0, 0)
        while hora <= fin_dia:
            ok = hora < fin_dia and self.perfil.get((est_id, dia_semana, hora.strftime("%H:%M")), 0) >= UMBRAL_OFERTA
            if ok and inicio_tramo is None:
                inicio_tramo = hora
            if not ok and inicio_tramo is not None:
                if hora - inicio_tramo >= timedelta(hours=2):
                    tramos.append((inicio_tramo, hora))
                inicio_tramo = None
            hora += BLOQUE
        return tramos

    def horario_recurrente(self, propietario, est_id, dias, hora_inicio, hora_fin, desde, hasta):
        """[PROPIA] Libera el mismo horario en varios días de la semana durante
        un rango de fechas. Regla: un bloqueo que el propietario ya hizo NO se
        pisa (esas horas se omiten). Devuelve (horas liberadas, horas omitidas)."""
        est = self.buscar_estacionamiento(est_id, propietario)
        if not dias:
            raise ValueError("Elija al menos un día.")
        if hora_fin <= hora_inicio:
            raise ValueError("La hora de término debe ser posterior a la de inicio.")
        if hasta < desde or (hasta - desde).days > 90:
            raise ValueError("Rango de fechas inválido (máximo 90 días).")
        limite = inicio_de_bloque(self.ahora())
        liberadas, omitidas = 0.0, 0.0
        dia = desde
        while dia <= hasta:
            if dia.weekday() in dias:
                for b in bloques(datetime.combine(dia, hora_inicio), datetime.combine(dia, hora_fin)):
                    if b < limite:
                        continue                       # no se libera el pasado
                    if b in est.bloques_bloqueados:
                        omitidas += 0.5                # el bloqueo del dueño se respeta
                    elif b not in est.bloques_liberados:
                        est.bloques_liberados.add(b)
                        liberadas += 0.5
            dia += timedelta(days=1)
        if liberadas == 0 and omitidas == 0:
            raise ValueError("El rango no genera ningún período nuevo.")
        texto_dias = ",".join(DIAS[d] for d in dias)
        self.registrar("HORARIO_RECURRENTE", propietario, estacionamiento=est_id,
                       inicio=datetime.combine(desde, hora_inicio), fin=datetime.combine(hasta, hora_fin),
                       detalle=f"{texto_dias} {hora_inicio:%H:%M}-{hora_fin:%H:%M}; {liberadas} h liberadas; "
                               f"{omitidas} h omitidas por bloqueo")
        self.guardar()
        return liberadas, omitidas

    # =======================================================================
    # CLIENTE
    # =======================================================================
    def validar_patente(self, patente):
        """Patente chilena: 4 letras + 2 números (ABCD12) o 2 letras + 4 números (AB1234)."""
        patente = patente.upper().replace("-", "").replace(" ", "")
        if not re.fullmatch(r"[A-Z]{4}\d{2}|[A-Z]{2}\d{4}", patente):
            raise ValueError(f"Patente {patente} inválida (formato ABCD12 o AB1234).")
        return patente

    def validar_vehiculo_libre(self, patente, inicio, fin):
        """Regla propia: un vehículo no puede tener dos reservas que se crucen."""
        for r in self.reservas:
            if r.patente == patente and r.esta_vigente() and r.se_cruza_con(inicio, fin):
                raise ValueError(f"El vehículo {patente} ya tiene la reserva {r.id} en ese horario.")

    def reservar(self, cliente, inicio, fin, patente="", est_elegido=""):
        """[Obligatoria] Crea una reserva PENDIENTE solo si hay un estacionamiento
        disponible. El estacionamiento queda retenido para que nadie más lo tome
        mientras el administrador confirma la asignación."""
        if cliente not in self.clientes:
            raise ValueError(f"No existe el cliente {cliente}.")
        patente = self.validar_patente(patente or self.clientes[cliente]["patente"])
        self.validar_periodo(inicio, fin, MAX_HORAS_RESERVA)
        self.validar_vehiculo_libre(patente, inicio, fin)
        opciones = [est_id for est_id, _ in self.opciones(inicio, fin)]
        if not opciones:
            self.registrar("SOLICITUD_RECHAZADA", cliente, inicio=inicio, fin=fin, cliente=cliente,
                           monto=self.precio(inicio, fin), detalle="sin estacionamiento disponible")
            raise ValueError("No hay estacionamientos disponibles en ese horario.")
        if est_elegido and est_elegido not in opciones:
            raise ValueError(f"{est_elegido} no está disponible en ese horario.")
        r = Reserva(self.nuevo_id_reserva(), cliente, patente, est_elegido or opciones[0],
                    inicio, fin, self.precio(inicio, fin))
        r.creada = self.ahora()
        self.reservas.append(r)
        self.registrar("CREACION", cliente, r)
        self.guardar()
        return r

    def cancelar(self, cliente, reserva_id):
        """[Obligatoria] Cancela antes del inicio. Devuelve el cargo cobrado:
        gratis con 2 h o más de anticipación (o si la reserva estaba AFECTADA);
        si no, 50 % del monto."""
        r = self.buscar_reserva(reserva_id, cliente)
        if not r.esta_vigente():
            raise ValueError(f"La reserva está {r.estado}; no se puede cancelar.")
        if self.ahora() >= r.inicio:
            raise ValueError("La reserva ya comenzó: use 'liberar anticipadamente'.")
        horas_antes = (r.inicio - self.ahora()).total_seconds() / 3600
        if r.estado == AFECTADA or horas_antes >= HORAS_CANCELACION_GRATIS:
            cargo = 0
        else:
            cargo = round(r.monto * RECARGO_CANCELACION)
        self.cobrar(r, cargo, CANCELADA)
        self.registrar("CANCELACION", cliente, r, monto=cargo, detalle=f"{horas_antes:.1f} h de anticipación")
        self.guardar()
        return cargo

    def liberar_reserva(self, cliente, reserva_id):
        """[Obligatoria] El cliente se va antes. Se cobran los bloques de 30 min
        usados (mínimo 1) y el resto del período queda libre para otros."""
        r = self.buscar_reserva(reserva_id, cliente)
        ahora = self.ahora()
        if not r.ocupa_estacionamiento():
            raise ValueError(f"La reserva está {r.estado}; no se puede liberar.")
        if ahora < r.inicio:
            raise ValueError("La reserva aún no comienza: use 'cancelar'.")
        if ahora >= r.fin:
            raise ValueError("La reserva ya terminó.")
        usados = max(1, len(bloques(r.inicio, ahora)))
        cargo = round(usados * TARIFA_BLOQUE * (1 - r.descuento))
        r.fin_real = ahora
        self.cobrar(r, cargo, LIBERADA)
        self.registrar("LIBERACION_ANTICIPADA", cliente, r, monto=cargo,
                       detalle=f"usó {usados} de {len(bloques(r.inicio, r.fin))} bloques")
        self.guardar()
        return cargo

    def reserva_recurrente(self, cliente, dias, hora_inicio, hora_fin, desde, hasta, patente=""):
        """[PROPIA] Reserva la misma franja en varios días.
        Reglas: todo o nada (si una fecha no tiene cupo, no se crea ninguna);
        se prefiere un mismo estacionamiento para toda la serie; 10 % de
        descuento con 4 o más reservas. Devuelve la lista de reservas creadas."""
        if cliente not in self.clientes:
            raise ValueError(f"No existe el cliente {cliente}.")
        patente = self.validar_patente(patente or self.clientes[cliente]["patente"])
        if hasta < desde or (hasta - desde).days > 60:
            raise ValueError("Rango de fechas inválido (máximo 60 días).")
        periodos = []
        dia = desde
        while dia <= hasta:
            if dia.weekday() in dias:
                periodos.append((datetime.combine(dia, hora_inicio), datetime.combine(dia, hora_fin)))
            dia += timedelta(days=1)
        if len(periodos) < 2:
            raise ValueError("Una reserva recurrente necesita al menos 2 fechas.")

        # 1) Validar todas las fechas antes de crear nada (todo o nada)
        opciones_por_fecha = []
        for inicio, fin in periodos:
            self.validar_periodo(inicio, fin, MAX_HORAS_RESERVA)
            self.validar_vehiculo_libre(patente, inicio, fin)
            ids = [est_id for est_id, _ in self.opciones(inicio, fin)]
            if not ids:
                self.registrar("SOLICITUD_RECHAZADA", cliente, inicio=inicio, fin=fin, cliente=cliente,
                               monto=self.precio(inicio, fin), detalle="reserva recurrente: una fecha sin cupo")
                raise ValueError(f"Serie rechazada: no hay cupo el {inicio:%d/%m}.")
            opciones_por_fecha.append(ids)

        # 2) ¿Hay un estacionamiento disponible en TODAS las fechas?
        comunes = [e for e in opciones_por_fecha[0] if all(e in ops for ops in opciones_por_fecha)]

        # 3) Crear las reservas
        descuento = DESCUENTO_RECURRENTE if len(periodos) >= 4 else 0.0
        serie = f"S{len({r.serie for r in self.reservas if r.serie}) + 1:03d}"
        creadas = []
        for (inicio, fin), ids in zip(periodos, opciones_por_fecha):
            est_id = comunes[0] if comunes else ids[0]
            r = Reserva(self.nuevo_id_reserva(), cliente, patente, est_id, inicio, fin,
                        self.precio(inicio, fin, descuento), PENDIENTE, "RECURRENTE", serie, descuento)
            r.creada = self.ahora()
            self.reservas.append(r)
            self.registrar("CREACION", cliente, r, detalle=f"serie {serie}")
            creadas.append(r)
        self.guardar()
        return creadas

    def cancelar_serie(self, cliente, serie):
        futuras = [r for r in self.reservas if r.serie == serie and r.cliente == cliente
                   and r.esta_vigente() and r.inicio > self.ahora()]
        if not futuras:
            raise ValueError("La serie no tiene reservas futuras.")
        return sum(self.cancelar(cliente, r.id) for r in futuras)

    # =======================================================================
    # ADMINISTRADOR
    # =======================================================================
    def alternativas(self, reserva):
        """Otros estacionamientos que sirven para lo que queda de la reserva."""
        desde = max(reserva.inicio, inicio_de_bloque(self.ahora()))
        excluir = reserva.estacionamiento if reserva.estado != PENDIENTE else ""
        return [est_id for est_id, _ in self.opciones(desde, reserva.fin, reserva, excluir)]

    def asignar(self, reserva_id, est_id="", actor="administrador"):
        """[Obligatoria] Confirma el estacionamiento de una reserva PENDIENTE:
        el que el sistema retuvo, u otro que esté disponible."""
        r = self.buscar_reserva(reserva_id)
        if r.estado != PENDIENTE:
            raise ValueError(f"Solo se asignan reservas PENDIENTES (está {r.estado}).")
        destino = est_id or r.estacionamiento
        self.buscar_estacionamiento(destino)
        desde = max(r.inicio, inicio_de_bloque(self.ahora()))
        motivo = self.motivo_no_disponible(destino, desde, r.fin, ignorar=r)
        if motivo:
            raise ValueError(f"No se puede usar {destino}: {motivo}.")
        anterior = r.estacionamiento if destino != r.estacionamiento else ""
        r.estacionamiento = destino
        r.estado = ASIGNADA
        self.registrar("ASIGNACION", actor, r, anterior=anterior)
        self.guardar()
        return r

    def reasignar(self, reserva_id, nuevo_est, motivo, actor="administrador"):
        """[Obligatoria] Cambia una reserva a otro estacionamiento disponible
        (por ejemplo, ante una contingencia). Si la reserva ya está en curso,
        se divide: el tramo usado queda en el estacionamiento original y el
        resto continúa en una reserva nueva, así cada dueño cobra lo suyo."""
        r = self.buscar_reserva(reserva_id)
        if not r.esta_vigente():
            raise ValueError(f"No se puede reasignar una reserva {r.estado}.")
        if r.fin <= self.ahora():
            raise ValueError("La reserva ya terminó.")
        if nuevo_est == r.estacionamiento and r.estado != AFECTADA:
            raise ValueError("La reserva ya está en ese estacionamiento.")
        self.buscar_estacionamiento(nuevo_est)
        corte = inicio_de_bloque(self.ahora())
        desde = max(r.inicio, corte)
        problema = self.motivo_no_disponible(nuevo_est, desde, r.fin, ignorar=r)
        if problema:
            raise ValueError(f"No se puede usar {nuevo_est}: {problema}.")

        anterior = r.estacionamiento
        if r.inicio < corte:
            # Reserva en curso: se cobra el tramo usado y se crea la continuación
            usado = round(len(bloques(r.inicio, corte)) * TARIFA_BLOQUE * (1 - r.descuento))
            r.fin_real = corte
            self.cobrar(r, usado, FINALIZADA)
            self.registrar("FINALIZACION", actor, r, monto=usado, detalle="tramo cerrado por reasignación")
            nueva = Reserva(self.nuevo_id_reserva(), r.cliente, r.patente, nuevo_est, corte, r.fin,
                            self.precio(corte, r.fin, r.descuento), ASIGNADA, r.tipo, r.serie, r.descuento)
            nueva.reserva_origen = r.id
            nueva.creada = self.ahora()
            self.reservas.append(nueva)
            r = nueva
        else:
            r.estacionamiento = nuevo_est
            r.estado = ASIGNADA
        self.registrar("REASIGNACION", actor, r, anterior=anterior, detalle=motivo)
        self.guardar()
        return r

    def compensar(self, reserva_id, actor="administrador"):
        """[PROPIA] Anula una reserva AFECTADA y da un crédito al cliente.
        Regla: solo se puede compensar si NO hay alternativa; si la hay,
        corresponde reasignar. El crédito (50 % del monto) se descuenta solo
        en el próximo cobro del cliente."""
        r = self.buscar_reserva(reserva_id)
        if r.estado != AFECTADA:
            raise ValueError("Solo se compensan reservas AFECTADAS por un bloqueo.")
        if r.fin > self.ahora():
            alternativas = self.alternativas(r)
            if alternativas:
                raise ValueError(f"Hay alternativa ({', '.join(alternativas[:3])}): corresponde reasignar.")
        credito = round(r.monto * PORCENTAJE_COMPENSACION)
        self.clientes[r.cliente]["credito"] += credito
        r.compensacion = credito
        r.estado = COMPENSADA
        self.registrar("COMPENSACION", actor, r, monto=credito)
        self.guardar()
        return credito

    def resolver(self, reserva, actor="administrador"):
        """Regla de contingencia para UNA reserva AFECTADA: reasignar al
        estacionamiento de menor riesgo si existe; si no, compensar."""
        alternativas = self.alternativas(reserva) if reserva.fin > self.ahora() else []
        if alternativas:
            nueva = self.reasignar(reserva.id, alternativas[0], "contingencia: regreso del propietario", actor)
            return f"{nueva.id} reasignada a {alternativas[0]}"
        credito = self.compensar(reserva.id, actor)
        return f"{reserva.id} compensada con crédito de ${credito:,}".replace(",", ".")

    def resolver_contingencias(self, actor="administrador"):
        """[PROPIA] Aplica la regla de contingencia a todas las reservas AFECTADAS."""
        afectadas = [r for r in self.reservas if r.estado == AFECTADA]
        return [self.resolver(r, actor) for r in afectadas]

    # =======================================================================
    # Actualización automática por el paso del tiempo (RN04)
    # =======================================================================
    def actualizar_estados(self):
        """Se ejecuta en cada vuelta del menú:
        - reservas cuyo período terminó -> FINALIZADA (se cobra el total);
        - PENDIENTES que llegaron a su inicio -> el sistema las asigna;
        - AFECTADAS que llegaron a su inicio sin resolver -> se resuelven."""
        ahora = self.ahora()
        cambios = 0
        for r in list(self.reservas):
            if r.ocupa_estacionamiento() and r.fin <= ahora:
                self.cobrar(r, r.monto, FINALIZADA)
                self.registrar("FINALIZACION", "sistema", r, monto=r.monto)
                cambios += 1
            elif r.estado == PENDIENTE and r.inicio <= ahora:
                self.asignar(r.id, actor="sistema")
                cambios += 1
            elif r.estado == AFECTADA and r.inicio <= ahora:
                self.resolver(r, actor="sistema")      # nadie la gestionó a tiempo
                cambios += 1
        if cambios:
            self.guardar()
        return cambios
